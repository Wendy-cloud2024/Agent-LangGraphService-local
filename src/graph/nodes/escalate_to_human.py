"""
转接人工节点

职责:
- 编制交接摘要 (问题, AI操作, 客户情感, 相关订单)
- 分配给可用人工客服
- 向客户发送转接通知
- 写入观测埋点
- 设置 resolution_status = "escalated"
- 如果是"接管"模式: 设置 session_takeover=True

接管模式 (takeover) 与普通转接的区别:
  - 普通 escalate_to_human: 仅当前消息转人工，下次AI仍会尝试处理
  - 接管 takeover: 设置 session_takeover=True，后续所有消息绕过AI直达人工
  - 接管模式下会向客户发送明确通知，并在 messages 中记录
  - 人工可通过 /end_takeover 命令释放接管
"""

import logging

from langchain_core.messages import AIMessage

from src.config.prompts import ESCALATION_SUMMARY_PROMPT
from src.utils.observability import TraceTimer, trace

logger = logging.getLogger(__name__)

# ==================== 接管模式预置消息 ====================
TAKEOVER_CUSTOMER_MSG = (
    "您好，由于您的问题较为复杂，我已为您转接专属人工客服。"
    "接下来将由人工客服全程为您服务，请稍候。"
)

TAKEOVER_RELEASE_MSG = (
    "人工客服已为您处理完毕，如果您还有其他问题，欢迎随时咨询。"
)


def escalate_to_human(state: dict) -> dict:
    """转接人工客服

    区分两种模式:
      - 普通转接: 仅转接当前问题，下次AI继续处理
      - 接管模式: session_takeover=True，后续所有消息直达人工
    """
    timer = TraceTimer()
    timer.start()
    trace_id = state.get("trace_id", "")

    # 判断是否为接管模式
    # 两种来源: (1) human_review 选择了 takeover (2) 已处于接管状态（checkpoint保留）
    is_takeover = state.get("human_decision") == "takeover" or state.get("session_takeover", False)

    # ============================================================
    # 1. 编制交接摘要 (给人工客服看)
    # ============================================================
    handoff_summary = _build_handoff_summary(state)

    # ============================================================
    # 2. 构建客户可见消息
    #    区分首次接管通知和后续接管模式下的消息
    # ============================================================
    already_in_takeover = state.get("session_takeover", False)
    if is_takeover and not already_in_takeover:
        # 首次接管：发送完整转接通知
        customer_msg = TAKEOVER_CUSTOMER_MSG
    elif already_in_takeover:
        # 后续消息（已在接管中）：简短提示
        customer_msg = "您的问题已转由人工客服处理，请稍候。"
    else:
        # 普通转接（非接管）
        customer_msg = (
            "您好，您的问题需要人工客服协助处理，"
            "正在为您转接，请稍候。"
        )

    # ============================================================
    # 3. 构建合并内容 (供日志/显示)
    # ============================================================
    merged = handoff_summary if is_takeover else customer_msg

    updates = {
        # 客户可见回复
        "draft_response": customer_msg,
        "merged_content": merged,
        # 状态更新
        "resolution_status": "escalated",
        "session_takeover": is_takeover,
        # 写入对话历史（确保下一轮能看到本轮转接消息）
        "messages": [AIMessage(content=customer_msg)],
        # 观测埋点
        "trace_events": [trace(trace_id, "escalate_to_human", "completed",
                               timer.elapsed_ms(),
                               {"is_takeover": is_takeover})],
    }

    # 接管模式额外记录交接摘要
    if is_takeover:
        logger.info(f"[{trace_id}] 人工接管会话，交接摘要长度: {len(handoff_summary)}")
    else:
        logger.info(f"[{trace_id}] 转接人工客服")

    return updates


def _build_handoff_summary(state: dict) -> str:
    """编制交接摘要

    包含:
    - 对话记录
    - 客户信息
    - AI已执行的步骤
    - 已尝试的方案
    - 客户画像
    - 人工审核员反馈（如有）
    """
    # 对话记录
    conversation_summary = ""
    for msg in state.get("messages", []):
        role = getattr(msg, "type", "unknown")
        content = getattr(msg, "content", str(msg))
        conversation_summary += f"[{role}] {content[:200]}\n"

    # 执行步骤
    trace_summary = ""
    for event in state.get("trace_events", []):
        trace_summary += f"- {event.get('node', '')}: {event.get('status', '')}\n"

    # 已尝试方案
    attempted_solutions = state.get("merged_content", "无")
    human_feedback = state.get("human_feedback", "")

    # 基础摘要
    summary = ESCALATION_SUMMARY_PROMPT.format(
        conversation_summary=conversation_summary[:1000],
        customer_id=state.get("customer_id", ""),
        customer_tier=state.get("customer_tier", ""),
        emotion=state.get("emotion", ""),
        trace_summary=trace_summary[:500],
        attempted_solutions=attempted_solutions[:500],
    )

    # 人工审核员反馈
    if human_feedback:
        summary += f"\n人工审核员反馈: {human_feedback}"

    # 客户画像 (Layer 4 记忆)
    customer_profile = state.get("customer_profile", {})
    if customer_profile and customer_profile.get("interaction_count", 0) > 0:
        summary += f"\n\n客户画像: 交互{customer_profile.get('interaction_count', 0)}次"
        summary += f", 等级={customer_profile.get('tier', '')}"
        summary += f", 频繁话题={customer_profile.get('frequent_topics', [])}"
        issues = customer_profile.get("issue_history", [])
        if issues:
            summary += f", 历史问题{len(issues)}条"

    return summary


def release_takeover(app, config: dict) -> dict | None:
    """释放接管状态

    人工客服调用此函数结束接管，恢复AI自动处理。
    使用 app.update_state() 重置 session_takeover=False。

    参数:
        app: 编译后的 supervisor graph
        config: 包含 thread_id 的配置

    返回:
        更新后的状态快照，失败返回 None
    """
    try:
        # 重置接管标记
        app.update_state(config, {"session_takeover": False}, as_node="escalate_to_human")

        # 发送释放通知消息
        app.update_state(
            config,
            {"messages": [AIMessage(content=TAKEOVER_RELEASE_MSG)]},
            as_node="respond_to_customer",
        )

        snapshot = app.get_state(config)
        logger.info(f"接管已释放，session_takeover={snapshot.values.get('session_takeover')}")
        return snapshot.values
    except Exception as e:
        logger.error(f"释放接管失败: {e}")
        return None
