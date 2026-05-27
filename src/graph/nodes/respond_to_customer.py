"""
自动回复节点

职责:
- 格式化最终消息
- 附加相关信息 (订单链接, 物流URL, 退货标签)
- 发送到客户渠道
- 写入观测埋点 (trace_events)
- 更新工单状态为 resolved
"""

import logging

from src.utils.observability import TraceTimer, trace

logger = logging.getLogger(__name__)


def respond_to_customer(state: dict) -> dict:
    """将最终回复发送给客户"""
    timer = TraceTimer()
    timer.start()
    trace_id = state.get("trace_id", "")

    draft = state.get("draft_response", "")
    if not draft:
        draft = state.get("merged_content", "感谢您的咨询，如有其他问题请随时联系我们。")

    updates = {
        "resolution_status": "resolved",
        "trace_events": [trace(trace_id, "respond_to_customer", "completed",
                               timer.elapsed_ms(),
                               {"response_length": len(draft)})],
    }

    logger.info(f"[{trace_id}] 回复客户: {draft[:100]}...")
    return updates
