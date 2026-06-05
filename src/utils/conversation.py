"""
对话上下文构建工具

从 LangGraph 累积的 messages 列表中构建最近几轮对话上下文，
供 LLM 分类、子图节点等使用。

修复 "无跨轮记忆" 问题: 所有子图和分类器都需要使用对话历史，
而非仅 messages[-1]。
"""


def build_conversation_context(messages: list, max_rounds: int = 4) -> list[dict]:
    """从messages列表构建最近几轮对话上下文，供LLM使用

    参数:
        messages: 完整消息列表（含 HumanMessage 和 AIMessage）
        max_rounds: 最多保留轮数（1轮 = 1条Human + 1条AI）

    返回:
        LLM可消费的 [{"role": ..., "content": ...}] 列表

    用法:
        # 在子图节点中
        from src.utils.conversation import build_conversation_context
        context = build_conversation_context(messages, max_rounds=3)
        response = llm.invoke([
            {"role": "system", "content": system_prompt},
            *context,
            {"role": "user", "content": last_msg},
        ])
    """
    max_msgs = max_rounds * 2
    recent = messages[-max_msgs:] if len(messages) > max_msgs else messages

    context = []
    for msg in recent:
        msg_type = getattr(msg, "type", None)
        content = getattr(msg, "content", str(msg))
        if msg_type == "human":
            context.append({"role": "user", "content": content})
        elif msg_type == "ai":
            context.append({"role": "assistant", "content": content})
        elif msg_type == "system":
            context.append({"role": "system", "content": content})
        # 跳过 tool 等其他类型
    return context
