"""
内容融合器

职责:
- 读取多个并行子图的 agent_findings
- 按优先级排序 (投诉 > 售后 > 售中 > 售前 > 通用)
- 按模板组装结构化答案
- 检测fallback标记 → 使用预置话术替代
- 保留引用标记
- 输出 merged_content
"""

import json
import logging

from src.config.settings import GENERATOR_MODEL
from src.config.llm import create_llm
from src.config.prompts import CONTENT_MERGER_PROMPT, FALLBACK_MESSAGES
from src.utils.observability import TraceTimer, trace

logger = logging.getLogger(__name__)

# 子图优先级排序
AGENT_PRIORITY = {
    "complaint_agent": 0,
    "aftersales_agent": 1,
    "insales_agent": 2,
    "presales_agent": 3,
    "general_agent": 4,
}


def content_merger(state: dict) -> dict:
    """融合多个子图的输出为统一回复"""
    timer = TraceTimer()
    timer.start()
    trace_id = state.get("trace_id", "")

    agent_findings = state.get("agent_findings", [])
    is_fallback = state.get("is_fallback", False)

    # 检查是否全部为降级结果
    all_fallback = all(f.get("result_type") == "fallback" for f in agent_findings) if agent_findings else False

    if is_fallback or all_fallback:
        # 降级处理: 使用预置话术
        reason = state.get("fallback_reason", "general")
        fallback_msg = FALLBACK_MESSAGES.get(reason, FALLBACK_MESSAGES["general"])
        updates = {
            "merged_content": fallback_msg,
            "is_fallback": True,
            "trace_events": [trace(trace_id, "content_merger", "completed",
                                   timer.elapsed_ms(),
                                   {"action": "fallback", "reason": reason})],
        }
        return updates

    # 按优先级排序子图结果
    sorted_findings = sorted(
        agent_findings,
        key=lambda f: AGENT_PRIORITY.get(f.get("source_agent", "general_agent"), 99),
    )

    # 处理fallback标记的子图: 使用预置话术替换
    processed_findings = []
    for finding in sorted_findings:
        if finding.get("result_type") == "fallback":
            reason = finding.get("fallback_reason", "general")
            fallback_msg = FALLBACK_MESSAGES.get(reason, FALLBACK_MESSAGES["general"])
            processed_findings.append({
                "source": finding.get("source_agent", "unknown"),
                "content": fallback_msg,
                "is_fallback": True,
            })
        elif finding.get("result_type") == "normal":
            processed_findings.append({
                "source": finding.get("source_agent", "unknown"),
                "content": finding.get("findings", {}),
                "is_fallback": False,
            })

    # 使用LLM融合内容
    llm = create_llm(GENERATOR_MODEL, temperature=0.3)
    try:
        prompt = CONTENT_MERGER_PROMPT.format(
            agent_findings=json.dumps(processed_findings, ensure_ascii=False, indent=2),
            intent_labels=json.dumps(state.get("intent_labels", []), ensure_ascii=False),
            emotion=state.get("emotion", "neutral"),
            customer_tier=state.get("customer_tier", "standard"),
        )
        response = llm.invoke([{"role": "user", "content": prompt}])
        merged = response.content
    except Exception as e:
        logger.error(f"内容融合失败: {e}")
        merged = "抱歉，系统处理中遇到了问题，请稍后再试。"

    updates = {
        "merged_content": merged,
        "trace_events": [trace(trace_id, "content_merger", "completed",
                               timer.elapsed_ms(),
                               {"findings_count": len(agent_findings)})],
    }
    return updates
