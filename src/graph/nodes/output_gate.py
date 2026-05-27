"""
输出关卡节点

三级路由:
  低风险 (risk=low, quality>=0.8) → respond_to_customer (全自动)
  中风险 (risk=medium, auto_correction_attempts<1) → tone_adapter (自动修正循环, 最多1次)
  中风险 (修正后仍不通过, attempts>=1) → human_review (直接升级为高风险)
  高风险 (risk=high, quality<0.5) → human_review (人工审核断点)
  关键 (risk=critical) → escalate_to_human

检查项: 安全(PII/有害内容), 质量评分, 风险评估
"""

import re
import json
import logging

from langchain_openai import ChatOpenAI

from src.config.settings import (
    CLASSIFIER_MODEL,
    QUALITY_SCORE_LOW,
    QUALITY_SCORE_CRITICAL,
    QUALITY_SCORE_REPROCESS,
    MAX_AUTO_CORRECTION_ATTEMPTS,
)
from src.config.prompts import OUTPUT_GATE_PROMPT
from src.utils.safety import full_safety_check
from src.utils.observability import TraceTimer, trace

logger = logging.getLogger(__name__)


def _parse_json_response(content: str) -> dict:
    """从LLM响应中提取JSON"""
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", content)
    if match:
        content = match.group(1).strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {}


def output_gate(state: dict) -> dict:
    """评估回复质量和安全性，确定风险等级"""
    timer = TraceTimer()
    timer.start()
    trace_id = state.get("trace_id", "")

    draft = state.get("draft_response", "")
    if not draft:
        draft = state.get("merged_content", "")

    # 安全检查
    safety_passed, safety_flags = full_safety_check(draft)

    # LLM质量评估
    quality_score = 0.0
    risk_level = "low"
    llm_flags = []
    try:
        llm = ChatOpenAI(model=CLASSIFIER_MODEL, temperature=0)
        prompt = OUTPUT_GATE_PROMPT.format(
            draft_response=draft,
            intent_labels=json.dumps(state.get("intent_labels", []), ensure_ascii=False),
            emotion=state.get("emotion", "neutral"),
        )
        response = llm.invoke([{"role": "user", "content": prompt}])
        result = _parse_json_response(response.content)
        quality_score = float(result.get("quality_score", 0.7))
        risk_level = result.get("risk_level", "low")
        llm_flags = result.get("safety_flags", [])
    except Exception as e:
        logger.error(f"质量评估失败: {e}")
        quality_score = 0.6
        risk_level = "medium"

    # 合并安全标记
    all_flags = safety_flags + llm_flags

    # 如果安全检查不通过，至少为中风险
    if not safety_passed:
        if risk_level == "low":
            risk_level = "medium"
        if "pii:" in str(all_flags):
            risk_level = "high"

    # 人工编辑/批准后的复查（v3安全闭环）
    human_decision = state.get("human_decision", "")
    if human_decision in ("approve", "edit"):
        # 人工修改后的内容也要过安全检查
        if not safety_passed:
            risk_level = "high"

    updates = {
        "quality_score": quality_score,
        "risk_level": risk_level,
        "safety_flags": all_flags,
        "requires_human_review": risk_level in ("high", "critical") or quality_score < QUALITY_SCORE_CRITICAL,
        "trace_events": [trace(trace_id, "output_gate", "completed",
                               timer.elapsed_ms(),
                               {"risk_level": risk_level,
                                "quality_score": quality_score,
                                "safety_passed": safety_passed})],
    }

    # 设置人工审核原因
    if updates["requires_human_review"]:
        reasons = []
        if risk_level == "critical":
            reasons.append("关键风险")
        elif risk_level == "high":
            reasons.append("高风险")
        if quality_score < QUALITY_SCORE_CRITICAL:
            reasons.append(f"质量评分过低({quality_score:.2f})")
        if all_flags:
            reasons.append(f"安全标记: {all_flags}")
        updates["human_review_reason"] = "; ".join(reasons)

    return updates


# ==================== 条件边: 三级路由 ====================

def three_way_route(state: dict) -> str:
    """output_gate后的三级路由决策"""
    risk_level = state.get("risk_level", "low")
    quality_score = state.get("quality_score", 0.8)
    auto_correction_attempts = state.get("auto_correction_attempts", 0)

    # 关键风险 → 直接转人工
    if risk_level == "critical":
        return "escalate_to_human"

    # 高风险 → 人工审核
    if risk_level == "high" or quality_score < QUALITY_SCORE_CRITICAL:
        return "human_review"

    # 中风险 → 自动修正（最多1次）
    if risk_level == "medium":
        if auto_correction_attempts < MAX_AUTO_CORRECTION_ATTEMPTS:
            return "tone_adapter"
        else:
            # v4: 修正后仍中/高风险 → 直接升级为高风险进human_review
            return "human_review"

    # 质量过低 → 重新处理
    if quality_score < QUALITY_SCORE_REPROCESS:
        resolution_attempts = state.get("resolution_attempts", 0)
        max_attempts = state.get("max_resolution_attempts", 3)
        if resolution_attempts < max_attempts:
            return "orchestrator_gate"

    # 低风险 → 自动发送
    return "respond_to_customer"
