"""
Supervisor中断协议 - 升级信号检测工具

提供共享的升级信号检测函数，供各子图在执行过程中判断是否需要升级:
  - detect_complaint_keywords(messages) → bool   投诉关键词检测
  - detect_emotion_escalation(emotion, intensity) → bool  极端情绪检测
  - check_tool_failures(tool_calls_made) → int    连续工具失败计数
  - evaluate_escalation(state, subgraph_context) → str|None  综合评估

信号类型:
  - "to_complaint" → 中断当前子图，路由到 complaint_agent
  - "to_human"    → 中断当前子图，路由到 escalate_to_human
  - None          → 无升级，继续正常流程
"""

import logging

from src.config.settings import (
    COMPLAINT_KEYWORDS,
    TOOL_FAILURE_THRESHOLD,
    EMOTION_INTENSITY_THRESHOLD,
)

logger = logging.getLogger(__name__)


def detect_complaint_keywords(messages: list, window: int = 6) -> bool:
    """检测最近客户消息中是否包含投诉关键词

    参数:
        messages: 消息列表
        window: 检查最近几条消息（默认6条，约3轮对话）

    返回:
        True 如果命中投诉关键词
    """
    recent_human_text = " ".join(
        getattr(m, "content", "")
        for m in messages[-window:]
        if getattr(m, "type", "") == "human"
    )
    return any(kw in recent_human_text for kw in COMPLAINT_KEYWORDS)


def detect_emotion_escalation(emotion: str, intensity: float) -> bool:
    """检测是否为极端负面情绪（触发升级）

    参数:
        emotion: 情感类别
        intensity: 情感强度 0-1

    返回:
        True 如果情绪强度超过阈值且为负面情绪
    """
    negative_emotions = ("angry", "frustrated", "furious", "disappointed")
    return intensity > EMOTION_INTENSITY_THRESHOLD and emotion in negative_emotions


def check_tool_failures(tool_calls_made: list) -> int:
    """统计连续工具调用失败次数

    从最近的工具调用往前计数，遇到非失败调用则停止。
    用于判断是否需要 escalate_to_human（连续2次失败）。

    参数:
        tool_calls_made: 工具调用记录列表

    返回:
        连续失败次数
    """
    if not tool_calls_made:
        return 0

    consecutive_failures = 0
    for call in reversed(tool_calls_made):
        # 检查工具调用状态
        status = call.get("status", "")
        if status in ("failed", "error", "pending_approval"):
            consecutive_failures += 1
        else:
            break  # 遇到成功调用则停止计数

    return consecutive_failures


def evaluate_escalation(state: dict, subgraph_context: dict | None = None) -> str | None:
    """综合评估是否需要发出升级信号

    评估优先级:
      1. 连续工具失败 ≥ TOOL_FAILURE_THRESHOLD → "to_human"
      2. 投诉关键词 → "to_complaint"
      3. 极端负面情绪 → "to_complaint"

    参数:
        state: 当前子图状态
        subgraph_context: 子图特定上下文（可选），如:
            - "refund_denied": 退款被拒标志（售后子图）
            - "order_severe_issue": 订单严重问题标志（售中子图）

    返回:
        "to_complaint" | "to_human" | None
    """
    trace_id = state.get("trace_id", "")
    messages = state.get("messages", [])
    emotion = state.get("emotion", "neutral")
    intensity = state.get("emotion_intensity", 0.3)
    tool_calls = state.get("tool_calls_made", [])

    # 优先级1: 连续工具失败 → escalate_to_human
    consecutive_failures = check_tool_failures(tool_calls)
    if consecutive_failures >= TOOL_FAILURE_THRESHOLD:
        logger.warning(
            f"[{trace_id}] 中断协议: 连续工具失败{consecutive_failures}次 ≥ {TOOL_FAILURE_THRESHOLD}, "
            f"发出 escalate_to_human 信号"
        )
        return "to_human"

    # 优先级2: 投诉关键词 → escalate_to_complaint
    if detect_complaint_keywords(messages):
        logger.info(f"[{trace_id}] 中断协议: 检测到投诉关键词, 发出 escalate_to_complaint 信号")
        return "to_complaint"

    # 优先级3: 极端负面情绪 → escalate_to_complaint
    if detect_emotion_escalation(emotion, intensity):
        logger.info(
            f"[{trace_id}] 中断协议: 极端负面情绪 {emotion}({intensity}), "
            f"发出 escalate_to_complaint 信号"
        )
        return "to_complaint"

    # 优先级4: 子图特定上下文检测
    if subgraph_context:
        # 售后: 退款被拒 + 情绪激动 → escalate_to_complaint
        if subgraph_context.get("refund_denied") and intensity > 0.6 and emotion in (
            "angry", "frustrated", "disappointed"
        ):
            logger.info(
                f"[{trace_id}] 中断协议: 退款被拒+情绪激动({emotion}/{intensity}), "
                f"发出 escalate_to_complaint 信号"
            )
            return "to_complaint"

        # 售中: 订单严重问题 + 情绪激动 → escalate_to_complaint
        if subgraph_context.get("order_severe_issue") and intensity > 0.6 and emotion in (
            "angry", "frustrated"
        ):
            logger.info(
                f"[{trace_id}] 中断协议: 订单严重问题+情绪激动({emotion}/{intensity}), "
                f"发出 escalate_to_complaint 信号"
            )
            return "to_complaint"

    return None
