"""
对话摘要压缩工具

当 messages 列表超过阈值时，将早期消息压缩为一条摘要 SystemMessage，
保留最近几轮对话不变。避免 token 无限增长的同时不丢失上下文。
"""

import logging
from langchain_core.messages import SystemMessage, BaseMessage

from src.config.settings import CLASSIFIER_MODEL
from src.config.llm import create_llm
from src.config.prompts import CONVERSATION_SUMMARY_PROMPT

logger = logging.getLogger(__name__)

# 触发摘要的消息数量阈值
SUMMARY_THRESHOLD = 16
# 摘要后保留的最近消息数
KEEP_RECENT = 8


def summarize_messages(messages: list[BaseMessage]) -> list[BaseMessage]:
    """将早期消息压缩为摘要，保留最近消息

    当 messages 数量 > SUMMARY_THRESHOLD 时触发:
    1. 取前 len - KEEP_RECENT 条消息
    2. 用 LLM 生成对话摘要
    3. 返回 [摘要SystemMessage] + 最近 KEEP_RECENT 条消息

    参数:
        messages: 当前对话消息列表

    返回:
        压缩后的消息列表
    """
    if len(messages) <= SUMMARY_THRESHOLD:
        return messages  # 不需要压缩

    old_messages = messages[:-KEEP_RECENT]
    recent_messages = messages[-KEEP_RECENT:]

    # 格式化早期消息供 LLM 摘要
    conversation_text = _format_messages(old_messages)

    try:
        llm = create_llm(CLASSIFIER_MODEL, temperature=0)
        prompt = CONVERSATION_SUMMARY_PROMPT.format(conversation=conversation_text[:3000])
        response = llm.invoke([{"role": "user", "content": prompt}])
        summary_text = response.content.strip()
    except Exception as e:
        logger.error("对话摘要生成失败: %s", e)
        # 降级: 只保留最后几条，不做摘要
        return recent_messages

    summary_msg = SystemMessage(content=f"[之前的对话摘要]\n{summary_text}")
    result = [summary_msg] + recent_messages

    logger.info("对话摘要压缩: %d 条 → %d 条 (摘要 + 最近%d条)",
                len(messages), len(result), KEEP_RECENT)
    return result


def _format_messages(messages: list[BaseMessage]) -> str:
    """将消息列表格式化为文本"""
    lines = []
    for msg in messages:
        role = getattr(msg, "type", "unknown")
        content = getattr(msg, "content", str(msg))
        lines.append(f"[{role}] {content[:200]}")
    return "\n".join(lines)
