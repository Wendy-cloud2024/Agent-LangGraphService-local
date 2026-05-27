"""
转接人工节点

职责:
- 编制交接摘要 (问题, AI操作, 客户情感, 相关订单)
- 分配给可用人工客服
- 向客户发送转接通知
- 写入观测埋点
- 设置 resolution_status = "escalated"
- 如果是"接管"模式: 设置 session_takeover=True
"""

import logging

from src.config.prompts import ESCALATION_SUMMARY_PROMPT
from src.utils.observability import TraceTimer, trace

logger = logging.getLogger(__name__)


def escalate_to_human(state: dict) -> dict:
    """转接人工客服"""
    timer = TraceTimer()
    timer.start()
    trace_id = state.get("trace_id", "")

    # 编制交接摘要
    conversation_summary = ""
    for msg in state.get("messages", []):
        role = getattr(msg, "type", "unknown")
        content = getattr(msg, "content", str(msg))
        conversation_summary += f"[{role}] {content[:200]}\n"

    trace_summary = ""
    for event in state.get("trace_events", []):
        trace_summary += f"- {event.get('node', '')}: {event.get('status', '')}\n"

    attempted_solutions = state.get("merged_content", "无")
    human_feedback = state.get("human_feedback", "")

    summary = ESCALATION_SUMMARY_PROMPT.format(
        conversation_summary=conversation_summary[:1000],
        customer_id=state.get("customer_id", ""),
        customer_tier=state.get("customer_tier", ""),
        emotion=state.get("emotion", ""),
        trace_summary=trace_summary[:500],
        attempted_solutions=attempted_solutions[:500],
    )

    if human_feedback:
        summary += f"\n人工审核员反馈: {human_feedback}"

    # 判断是否为接管模式
    is_takeover = state.get("human_decision") == "takeover"

    updates = {
        "resolution_status": "escalated",
        "session_takeover": is_takeover,
        "trace_events": [trace(trace_id, "escalate_to_human", "completed",
                               timer.elapsed_ms(),
                               {"is_takeover": is_takeover})],
    }

    logger.info(f"[{trace_id}] 转接人工客服, 接管模式={is_takeover}")
    return updates
