"""
自动回复节点

职责:
- 格式化最终消息
- 附加相关信息 (订单链接, 物流URL, 退货标签)
- 发送到客户渠道
- 将AI回复写入messages（关键：维持对话历史的完整性）
- 写入观测埋点 (trace_events)
- 更新工单状态为 resolved
"""

import logging

from langchain_core.messages import AIMessage

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
        # 关键修复: 将AI回复写入messages，确保下一轮对话能看到本轮回答
        # add_messages reducer 会自动追加，不会覆盖已有消息
        "messages": [AIMessage(content=draft)],
        "resolution_status": "resolved",
        "trace_events": [trace(trace_id, "respond_to_customer", "completed",
                               timer.elapsed_ms(),
                               {"response_length": len(draft)})],
    }

    # Layer 4: 对话结束时更新客户画像
    try:
        from src.memory.customer_store import get_customer_store
        customer_id = state.get("customer_id", "")
        if customer_id:
            store = get_customer_store()
            updated_profile = store.update_from_interaction(customer_id, state)
            updates["customer_profile"] = updated_profile
    except Exception as e:
        logger.warning("更新客户画像失败: %s", e)

    logger.info(f"[{trace_id}] 回复客户: {draft[:100]}...")
    return updates
