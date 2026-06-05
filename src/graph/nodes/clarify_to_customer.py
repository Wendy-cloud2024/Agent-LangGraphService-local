"""
澄清追问旁路节点

独立于主线路径, 绕过 content_merger/tone_adapter/output_gate。

流程:
- 从 clarification_request 生成追问消息
- 仅做基本安全检查 (PII过滤, 有害内容检测)
- 直接发送给客户
- 设置 pending_clarification=True + pending_subgraph + pending_accumulated_state
- 客户回复后由 orchestrator_gate 第⓪步捕获并路由回原子图
"""

import logging

from langchain_core.messages import AIMessage

from src.config.settings import GENERATOR_MODEL
from src.config.llm import create_llm
from src.config.prompts import CLARIFICATION_PROMPT
from src.utils.safety import basic_safety_check
from src.utils.observability import TraceTimer, trace

logger = logging.getLogger(__name__)


def clarify_to_customer(state: dict) -> dict:
    """生成澄清追问并直接发送给客户"""
    timer = TraceTimer()
    timer.start()
    trace_id = state.get("trace_id", "")

    clarification_request = state.get("clarification_request", {})
    question = clarification_request.get("question", "")
    required_info = clarification_request.get("required_info", "")

    # 生成追问消息
    try:
        llm = create_llm(GENERATOR_MODEL, temperature=0.3)
        prompt = CLARIFICATION_PROMPT.format(
            question=question,
            required_info=required_info,
        )
        response = llm.invoke([{"role": "user", "content": prompt}])
        clarification_msg = response.content
    except Exception as e:
        logger.error(f"生成追问消息失败: {e}")
        clarification_msg = f"请提供以下信息以便我继续为您服务: {required_info or question}"

    # 仅做基本安全检查
    passed, flags = basic_safety_check(clarification_msg)
    if not passed:
        logger.warning(f"[{trace_id}] 澄清消息安全检查不通过: {flags}")
        clarification_msg = f"请提供以下信息以便我继续为您服务: {required_info or question}"

    # 确定挂起的子图
    pending_subgraph = ""
    for label in state.get("intent_labels", []):
        if label.get("primary"):
            from src.config.settings import INTENT_TO_SUBGRAPH
            intent = label.get("intent", "")
            pending_subgraph = INTENT_TO_SUBGRAPH.get(intent, "general_agent")
            break

    if not pending_subgraph:
        pending_subgraph = "general_agent"

    # 保存挂起状态
    clarification_attempts = state.get("clarification_attempts", 0) + 1

    updates = {
        # 将澄清追问写入messages，维持对话历史完整性
        "messages": [AIMessage(content=clarification_msg)],
        "pending_clarification": True,
        "pending_subgraph": pending_subgraph,
        "pending_clarification_intent": state.get("intent_labels", [{}])[0].get("intent", ""),
        "pending_accumulated_state": {
            "intent_labels": state.get("intent_labels", []),
            "emotion": state.get("emotion", ""),
            "customer_tier": state.get("customer_tier", ""),
            "clarification_request": clarification_request,
        },
        "clarification_attempts": clarification_attempts,
        "draft_response": clarification_msg,
        "resolution_status": "clarifying",
        "trace_events": [trace(trace_id, "clarify_to_customer", "completed",
                               timer.elapsed_ms(),
                               {"pending_subgraph": pending_subgraph,
                                "attempts": clarification_attempts})],
    }

    logger.info(f"[{trace_id}] 发送澄清追问: {clarification_msg[:100]}... "
                f"(子图={pending_subgraph}, 第{clarification_attempts}次)")
    return updates
