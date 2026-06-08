"""
子图上下文注入包装器 + Supervisor中断协议

在 supervisor 调用子图前，通过 inject_subgraph_context() 注入相关历史。
子图通过 state["relevant_history"] 获取上下文，无需直接访问外部存储。

Supervisor中断协议:
  - 超时处理: 子图执行超过 SUBGRAPH_TIMEOUT_SECONDS → 返回 fallback 结果
  - 错误边界: try/except 包裹 invoke → 异常时返回 fallback
  - 投诉子图特殊: 不降级，异常直接 escalate_to_human
  - 保存被中断子图的部分结果到 interrupted_subgraph_results

用法:
    graph.add_node("presales_agent",
        create_subgraph_node("presales_agent", compile_presales_subgraph()))
"""

import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

from src.tools.context_injection import inject_subgraph_context
from src.utils.observability import TraceTimer, trace
from src.config.settings import SUBGRAPH_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)

# 投诉子图名称集合 — 异常时不走 fallback，直接 escalate_to_human
NO_FALLBACK_SUBGRAPHS = {"complaint_agent"}


def create_subgraph_node(subgraph_name: str, compiled_subgraph):
    """创建带上下文注入 + 超时 + 错误边界的子图节点

    参数:
        subgraph_name: 子图名称 (presales_agent / insales_agent / ...)
        compiled_subgraph: 编译后的子图
    """

    def node_fn(state: dict) -> dict:
        timer = TraceTimer()
        timer.start()
        trace_id = state.get("trace_id", "")

        # 1. 注入上下文
        try:
            context = inject_subgraph_context(state, subgraph_name)
            relevant_history = context.get("relevant_history", [])
            logger.info(f"[{trace_id}] 上下文注入到 {subgraph_name}: {len(relevant_history)} 条")
        except Exception as e:
            logger.error(f"上下文注入失败 ({subgraph_name}): {e}")
            relevant_history = []

        # 2. 合并到 state (不修改原始 state, 构建 enriched 副本)
        enriched_state = dict(state)
        enriched_state["relevant_history"] = relevant_history

        # 3. 执行子图（带超时和错误边界）
        result = _execute_with_protection(
            subgraph_name, compiled_subgraph, enriched_state, trace_id, timer
        )

        return result

    # 保留子图名称方便调试
    node_fn.__name__ = subgraph_name
    return node_fn


def _execute_with_protection(
    subgraph_name: str,
    compiled_subgraph,
    enriched_state: dict,
    trace_id: str,
    timer: TraceTimer,
) -> dict:
    """带超时和错误边界的子图执行

    执行策略:
      - 使用 ThreadPoolExecutor + 超时控制
      - 正常完成 → 返回子图结果
      - 超时 → fallback 预置话术 / 投诉子图 → escalate_to_human
      - 异常 → fallback 预置话术 / 投诉子图 → escalate_to_human
    """
    is_no_fallback = subgraph_name in NO_FALLBACK_SUBGRAPHS

    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(compiled_subgraph.invoke, enriched_state)
            try:
                result = future.result(timeout=SUBGRAPH_TIMEOUT_SECONDS)
            except FuturesTimeoutError:
                # 超时处理
                elapsed = timer.elapsed_ms()
                logger.warning(
                    f"[{trace_id}] 中断协议: {subgraph_name} 执行超时 "
                    f"({elapsed}ms > {SUBGRAPH_TIMEOUT_SECONDS}s)"
                )

                if is_no_fallback:
                    # 投诉子图不降级，直接升级到人工
                    return _create_escalate_to_human_result(
                        subgraph_name, trace_id, timer,
                        reason="timeout", elapsed_ms=elapsed,
                    )
                else:
                    # 其他子图走 fallback
                    return _create_fallback_result(
                        subgraph_name, trace_id, timer,
                        reason="timeout", elapsed_ms=elapsed,
                    )

        # 正常完成
        if result is None:
            result = {}
        result.setdefault("trace_events", [
            trace(trace_id, subgraph_name, "completed", timer.elapsed_ms(),
                  {"context_injected": len(enriched_state.get("relevant_history", []))})
        ])
        return result

    except Exception as e:
        # 异常处理
        elapsed = timer.elapsed_ms()
        logger.error(
            f"[{trace_id}] 中断协议: {subgraph_name} 执行异常: {e}",
            exc_info=True,
        )

        if is_no_fallback:
            # 投诉子图不降级，直接升级到人工
            return _create_escalate_to_human_result(
                subgraph_name, trace_id, timer,
                reason=f"exception: {type(e).__name__}", elapsed_ms=elapsed,
            )
        else:
            # 其他子图走 fallback
            return _create_fallback_result(
                subgraph_name, trace_id, timer,
                reason=f"exception: {type(e).__name__}", elapsed_ms=elapsed,
            )


def _create_fallback_result(
    subgraph_name: str,
    trace_id: str,
    timer: TraceTimer,
    reason: str,
    elapsed_ms: float,
) -> dict:
    """创建 fallback 降级结果

    子图超时或异常时，返回预置话术替代真实结果。
    fallback 结果会被 subgraph_output_router 标记并在 content_merger 中用预置话术替换。
    """
    fallback_messages = {
        "presales_agent": "抱歉，商品查询系统暂时繁忙，请稍后再试或回复'人工客服'获取帮助。",
        "insales_agent": "抱歉，订单查询系统暂时繁忙，请稍后再试或回复'人工客服'获取帮助。",
        "aftersales_agent": "抱歉，售后服务系统暂时繁忙，请稍后再试或回复'人工客服'获取帮助。",
        "general_agent": "抱歉，系统暂时无法处理您的问题，请稍后再试或回复'人工客服'获取帮助。",
    }
    fallback_msg = fallback_messages.get(
        subgraph_name,
        "抱歉，系统暂时无法处理，请稍后再试或回复'人工客服'获取帮助。"
    )

    logger.info(f"[{trace_id}] {subgraph_name} 降级为 fallback: {reason}")

    return {
        "agent_findings": [{
            "source_agent": subgraph_name,
            "result_type": "fallback",
            "findings": {"answer": fallback_msg},
            "fallback_reason": reason,
            "fallback_message": fallback_msg,
            "clarification_request": None,
            "escalate_signal": None,
        }],
        "is_fallback": True,
        "fallback_reason": f"{subgraph_name}: {reason}",
        "trace_events": [trace(trace_id, subgraph_name, "fallback", elapsed_ms,
                               {"reason": reason})],
    }


def _create_escalate_to_human_result(
    subgraph_name: str,
    trace_id: str,
    timer: TraceTimer,
    reason: str,
    elapsed_ms: float,
) -> dict:
    """投诉子图专用: 异常时不走 fallback，直接 escalate_to_human

    投诉子图不降级（投诉必须处理），异常时直接转人工经理。
    """
    logger.warning(
        f"[{trace_id}] 中断协议: {subgraph_name} 异常({reason}), "
        f"投诉子图不降级, 直接 escalate_to_human"
    )

    return {
        "agent_findings": [{
            "source_agent": subgraph_name,
            "result_type": "normal",
            "findings": {
                "answer": "投诉处理过程中遇到问题，正在为您转接人工经理。",
                "escalate_reason": reason,
            },
            "clarification_request": None,
            "escalate_signal": "to_human",
        }],
        "escalate_signal": "to_human",
        "interrupted_subgraph_results": [],
        "trace_events": [trace(trace_id, subgraph_name, "escalate_to_human", elapsed_ms,
                               {"reason": reason})],
    }
