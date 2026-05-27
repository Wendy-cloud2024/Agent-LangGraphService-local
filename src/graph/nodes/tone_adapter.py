"""
语气与合规适配器

职责:
- 根据 emotion/customer_tier 调整语气
- 应用 strategy_version 对应的 prompt 变体 (A/B测试)
- 根据品牌调性调整措辞
- 标注引用来源
- 支持 output_gate 中风险自动修正时的改写指导
- 输出 draft_response
"""

import logging

from langchain_openai import ChatOpenAI

from src.config.settings import ADAPTER_MODEL, LLM_BASE_URL
from src.config.prompts import TONE_ADAPTER_PROMPT
from src.utils.observability import TraceTimer, trace

logger = logging.getLogger(__name__)


def tone_adapter(state: dict) -> dict:
    """根据客户情感和等级调整回复语气"""
    timer = TraceTimer()
    timer.start()
    trace_id = state.get("trace_id", "")

    merged_content = state.get("merged_content", "")
    if not merged_content:
        return {
            "draft_response": "",
            "trace_events": [trace(trace_id, "tone_adapter", "completed",
                                   timer.elapsed_ms(), {"action": "empty_input"})],
        }

    llm = ChatOpenAI(model=ADAPTER_MODEL, temperature=0.3, base_url=LLM_BASE_URL)
    try:
        prompt = TONE_ADAPTER_PROMPT.format(
            emotion=state.get("emotion", "neutral"),
            emotion_intensity=state.get("emotion_intensity", 0.3),
            customer_tier=state.get("customer_tier", "standard"),
            urgency=state.get("urgency", "low"),
            draft_response=merged_content,
        )
        response = llm.invoke([{"role": "user", "content": prompt}])
        adapted = response.content
    except Exception as e:
        logger.error(f"语气适配失败: {e}")
        adapted = merged_content

    # 递增自动修正次数
    correction_attempts = state.get("auto_correction_attempts", 0) + 1

    updates = {
        "draft_response": adapted,
        "auto_correction_attempts": correction_attempts,
        "trace_events": [trace(trace_id, "tone_adapter", "completed",
                               timer.elapsed_ms(),
                               {"correction_attempt": correction_attempts})],
    }
    return updates
