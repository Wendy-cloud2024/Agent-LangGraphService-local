"""
人工审核断点节点

LangGraph interrupt() 实现, 暂停执行等待人工决策。

人工决策5种:
  批准 → output_gate复查 → respond_to_customer
  编辑 → output_gate复查 → respond_to_customer
  拒绝-重生成 → content_merger (沿用子图结果重新生成)
  拒绝-重分诊 → orchestrator_gate (轻量模式, 仅重做意图分类)
  接管 → escalate_to_human + 设置session_takeover=True

安全闭环: 人工输出必须过output_gate复查, 最多2轮防死循环。
"""

import logging

from langgraph.types import interrupt

from src.config.settings import MAX_HUMAN_REVIEW_ROUNDS
from src.utils.observability import TraceTimer, trace

logger = logging.getLogger(__name__)


def human_review(state: dict) -> dict:
    """人工审核断点 - 暂停执行等待人工决策"""
    timer = TraceTimer()
    timer.start()
    trace_id = state.get("trace_id", "")

    review_rounds = state.get("human_review_rounds", 0)

    # 安全检查: 防止无限循环
    if review_rounds >= MAX_HUMAN_REVIEW_ROUNDS:
        logger.warning(f"[{trace_id}] 人工审核轮次超过上限({review_rounds})，强制转人工")
        return {
            "human_decision": "takeover",
            "trace_events": [trace(trace_id, "human_review", "completed",
                                   timer.elapsed_ms(),
                                   {"action": "force_escalate",
                                    "rounds": review_rounds})],
        }

    # 构建审核信息
    review_info = {
        "draft_response": state.get("draft_response", ""),
        "risk_level": state.get("risk_level", ""),
        "quality_score": state.get("quality_score", 0),
        "safety_flags": state.get("safety_flags", []),
        "human_review_reason": state.get("human_review_reason", ""),
        "review_round": review_rounds + 1,
    }

    # 触发中断，等待人工决策
    decision = interrupt(review_info)

    # 解析人工决策
    human_decision = decision.get("decision", "approve")
    human_feedback = decision.get("feedback", "")
    edited_response = decision.get("edited_response", "")

    updates = {
        "human_decision": human_decision,
        "human_feedback": human_feedback,
        "human_review_rounds": review_rounds + 1,
        "trace_events": [trace(trace_id, "human_review", "completed",
                               timer.elapsed_ms(),
                               {"decision": human_decision,
                                "round": review_rounds + 1})],
    }

    # 根据决策更新内容
    if human_decision == "edit" and edited_response:
        updates["draft_response"] = edited_response
    elif human_decision == "approve":
        pass  # 保持当前draft_response
    elif human_decision == "reject_regenerate":
        pass  # 路由到content_merger重新生成
    elif human_decision == "reject_reclassify":
        pass  # 路由到orchestrator_gate轻量模式
    elif human_decision == "takeover":
        updates["session_takeover"] = True

    logger.info(f"[{trace_id}] 人工审核决策: {human_decision} (第{review_rounds + 1}轮)")
    return updates


def route_after_human_review(state: dict) -> str:
    """人工审核后的路由决策"""
    decision = state.get("human_decision", "approve")
    review_rounds = state.get("human_review_rounds", 0)

    if decision == "takeover":
        return "escalate_to_human"

    if decision == "reject_regenerate":
        return "content_merger"

    if decision == "reject_reclassify":
        return "orchestrator_gate"

    # 批准或编辑 → output_gate复查
    return "output_gate"
