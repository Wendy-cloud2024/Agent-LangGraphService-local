"""
子图输出统一路由器

接收所有并行子图的输出, 按优先级依次检查:
  优先级1: escalate信号 → 中断其他子图 → complaint_agent或escalate_to_human
  优先级2: clarification_request → clarify_to_customer (忽略其他结果)
  优先级3: fallback标记 → 预置话术替换, 与正常结果一起进merger
  优先级4: 全部正常 → content_merger
"""

import logging

from src.config.settings import MAX_CLARIFICATION_ATTEMPTS
from src.utils.observability import TraceTimer, trace

logger = logging.getLogger(__name__)


def subgraph_output_router(state: dict) -> dict:
    """统一路由所有子图输出"""
    timer = TraceTimer()
    timer.start()
    trace_id = state.get("trace_id", "")

    agent_findings = state.get("agent_findings", [])
    updates = {}

    # 优先级1: 中断信号（最高优先级）
    escalate_results = [f for f in agent_findings if f.get("escalate_signal")]
    if escalate_results:
        signal = escalate_results[0]["escalate_signal"]
        updates["escalate_signal"] = signal
        updates["interrupted_subgraph_results"] = [
            f for f in agent_findings if not f.get("escalate_signal")
        ]
        updates["trace_events"] = [trace(trace_id, "subgraph_output_router", "completed",
                                         timer.elapsed_ms(),
                                         {"action": "escalate", "signal": signal})]
        logger.info(f"[{trace_id}] 检测到升级信号: {signal}")
        return updates

    # 优先级2: 澄清请求
    clarification_results = [
        f for f in agent_findings if f.get("result_type") == "clarification"
    ]
    if clarification_results:
        clarification_attempts = state.get("clarification_attempts", 0)
        if clarification_attempts < MAX_CLARIFICATION_ATTEMPTS:
            updates["clarification_request"] = clarification_results[0].get(
                "clarification_request", {}
            )
            updates["trace_events"] = [trace(trace_id, "subgraph_output_router", "completed",
                                             timer.elapsed_ms(),
                                             {"action": "clarification"})]
            return updates
        else:
            # 澄清2次仍不足 → 转人工
            updates["trace_events"] = [trace(trace_id, "subgraph_output_router", "completed",
                                             timer.elapsed_ms(),
                                             {"action": "clarification_exceeded"})]
            updates["requires_human_review"] = True
            updates["human_review_reason"] = "澄清次数超过上限，转人工处理"
            return updates

    # 优先级3: 降级处理 - 标记fallback
    has_fallback = False
    for f in agent_findings:
        if f.get("result_type") == "fallback":
            f["use_preset"] = True
            has_fallback = True

    if has_fallback:
        updates["is_fallback"] = True
        updates["fallback_reason"] = "subgraph_fallback"

    # 优先级4: 全部正常 → 继续到content_merger
    updates["trace_events"] = [trace(trace_id, "subgraph_output_router", "completed",
                                     timer.elapsed_ms(),
                                     {"action": "normal",
                                      "has_fallback": has_fallback})]
    return updates


def route_after_output_router(state: dict) -> str:
    """subgraph_output_router后的条件路由"""
    # 检查升级信号
    signal = state.get("escalate_signal")
    if signal:
        if signal == "to_complaint":
            return "complaint_agent"
        return "escalate_to_human"

    # 检查澄清请求
    if state.get("clarification_request"):
        clarification_attempts = state.get("clarification_attempts", 0)
        if clarification_attempts < MAX_CLARIFICATION_ATTEMPTS:
            return "clarify_to_customer"
        else:
            return "escalate_to_human"

    # 检查是否需要转人工（澄清超限）
    if state.get("requires_human_review") and not state.get("agent_findings"):
        return "escalate_to_human"

    # 正常流程 → content_merger
    return "content_merger"
