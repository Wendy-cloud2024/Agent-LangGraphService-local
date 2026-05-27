"""
统一入口关卡节点

处理步骤:
  ⓪ 前置状态检查 (pending_clarification → 直接路由回原子图)
  ① 安全审核 (敏感词/有害内容 → 旁路)
  ② 转人工快捷匹配 (规则正则, 零延迟)
  ③ 多模态轻量预处理 (仅安全检查+通用描述)
  ④ 语言检测
  ⑤ 轻量历史加载 (最近3轮摘要)
  ⑥ 多维标签分类 (intent_labels)
  ⑦ 情感检测 + 紧急度
  ⑧ 路由决策 (active_agents)
"""

import re
import json
import logging

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from src.config.settings import (
    CLASSIFIER_MODEL,
    HUMAN_TRANSFER_PATTERNS,
    EMOTION_INTENSITY_THRESHOLD,
    INTENT_CATEGORIES,
    INTENT_TO_SUBGRAPH,
    HISTORY_WINDOW_ROUNDS,
)
from src.config.prompts import (
    INTENT_CLASSIFICATION_PROMPT,
    EMOTION_DETECTION_PROMPT,
    ROUTING_DECISION_PROMPT,
)
from src.utils.safety import check_sensitive_words, check_image_safety
from src.utils.observability import TraceTimer, trace

logger = logging.getLogger(__name__)


def _detect_language(text: str) -> str:
    """简单语言检测"""
    # 中文字符占比
    zh_chars = len(re.findall(r"[一-鿿]", text))
    en_chars = len(re.findall(r"[a-zA-Z]", text))
    total = zh_chars + en_chars
    if total == 0:
        return "zh"
    if zh_chars / total > 0.3:
        return "zh"
    return "en"


def _match_human_transfer(text: str) -> bool:
    """转人工快捷匹配（规则优先，不经LLM）"""
    for pattern in HUMAN_TRANSFER_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def _parse_json_response(content: str) -> dict:
    """从LLM响应中提取JSON"""
    # 尝试提取 ```json ... ``` 代码块
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", content)
    if match:
        content = match.group(1).strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        logger.warning(f"JSON解析失败: {content[:200]}")
        return {}


def orchestrator_gate(state: dict) -> dict:
    """统一入口关卡

    执行8步处理流程，返回更新后的状态字段。
    """
    timer = TraceTimer()
    timer.start()
    trace_id = state.get("trace_id", "")

    # 获取最新客户消息
    messages = state.get("messages", [])
    if not messages:
        return {}
    last_message = messages[-1]
    customer_text = last_message.content if hasattr(last_message, "content") else str(last_message)

    updates = {}

    # ============================================================
    # ⓪ 前置状态检查: 澄清重入
    # ============================================================
    if state.get("pending_clarification"):
        logger.info(f"[{trace_id}] 检测到pending_clarification, 跳过全部分诊, 路由到 {state.get('pending_subgraph')}")
        updates["trace_events"] = [trace(trace_id, "orchestrator_gate", "completed",
                                         timer.elapsed_ms(),
                                         {"action": "clarification_reentry",
                                          "subgraph": state.get("pending_subgraph")})]
        return updates

    # ============================================================
    # ① 安全审核
    # ============================================================
    sensitive_hit, sensitive_words = check_sensitive_words(customer_text)
    updates["sensitive_word_hit"] = sensitive_hit

    # 图片安全审核
    media_safety = True
    media_desc = ""
    if hasattr(last_message, "additional_kwargs") and "images" in last_message.additional_kwargs:
        for img in last_message.additional_kwargs["images"]:
            safe, desc = check_image_safety(img)
            if not safe:
                media_safety = False
                media_desc = desc
                break

    updates["media_safety_passed"] = media_safety
    updates["media_lightweight_description"] = media_desc

    # 不通过则直接标记
    safety_passed = not sensitive_hit and media_safety
    updates["safety_screen_passed"] = safety_passed

    if not safety_passed:
        updates["trace_events"] = [trace(trace_id, "orchestrator_gate", "completed",
                                         timer.elapsed_ms(),
                                         {"action": "safety_bypass",
                                          "sensitive_words": sensitive_words,
                                          "media_safe": media_safety})]
        # 敏感词命中路由到投诉子图
        if sensitive_hit:
            updates["active_agents"] = ["complaint_agent"]
            updates["routing_reason"] = f"敏感词命中: {sensitive_words}"
            updates["emotion"] = "angry"
            updates["emotion_intensity"] = 0.8
            updates["urgency"] = "high"
        return updates

    # ============================================================
    # ② 转人工快捷匹配
    # ============================================================
    if _match_human_transfer(customer_text):
        logger.info(f"[{trace_id}] 转人工快捷匹配命中")
        updates["active_agents"] = ["escalate_to_human"]
        updates["routing_reason"] = "客户要求转人工"
        updates["trace_events"] = [trace(trace_id, "orchestrator_gate", "completed",
                                         timer.elapsed_ms(),
                                         {"action": "human_transfer_shortcut"})]
        return updates

    # 检查会话接管状态
    if state.get("session_takeover"):
        updates["active_agents"] = ["escalate_to_human"]
        updates["routing_reason"] = "会话已被人工客服接管"
        updates["trace_events"] = [trace(trace_id, "orchestrator_gate", "completed",
                                         timer.elapsed_ms(),
                                         {"action": "session_takeover"})]
        return updates

    # ============================================================
    # ③④⑤⑥⑦⑧ 需要LLM的处理步骤
    # ============================================================
    llm = ChatOpenAI(model=CLASSIFIER_MODEL, temperature=0)

    # ④ 语言检测（规则匹配，不需要LLM）
    updates["language"] = _detect_language(customer_text)

    # ⑥ 多维标签分类
    intent_result = {}
    try:
        categories_str = "\n".join(f"  - {c}" for c in INTENT_CATEGORIES)
        prompt = INTENT_CLASSIFICATION_PROMPT.format(intent_categories=categories_str)
        response = llm.invoke([
            {"role": "system", "content": prompt},
            {"role": "user", "content": customer_text},
        ])
        intent_result = _parse_json_response(response.content)
    except Exception as e:
        logger.error(f"意图分类失败: {e}")

    intent_labels = intent_result.get("intent_labels", [])
    if not intent_labels:
        intent_labels = [{"intent": "general_faq", "confidence": 0.5, "primary": True}]
    updates["intent_labels"] = intent_labels

    # ⑦ 情感检测 + 紧急度
    emotion_result = {}
    try:
        response = llm.invoke([
            {"role": "system", "content": EMOTION_DETECTION_PROMPT},
            {"role": "user", "content": customer_text},
        ])
        emotion_result = _parse_json_response(response.content)
    except Exception as e:
        logger.error(f"情感检测失败: {e}")

    updates["emotion"] = emotion_result.get("emotion", "neutral")
    updates["emotion_intensity"] = float(emotion_result.get("emotion_intensity", 0.3))
    updates["urgency"] = emotion_result.get("urgency", "low")

    # ============================================================
    # ⑧ 路由决策
    # ============================================================
    # 先检查极端情感旁路
    emotion_val = updates.get("emotion", "neutral")
    intensity_val = updates.get("emotion_intensity", 0.3)
    if intensity_val > EMOTION_INTENSITY_THRESHOLD and emotion_val in ("angry", "frustrated"):
        updates["active_agents"] = ["complaint_agent"]
        updates["routing_reason"] = f"极端情感旁路: {emotion_val}(强度{intensity_val})"
        updates["trace_events"] = [trace(trace_id, "orchestrator_gate", "completed",
                                         timer.elapsed_ms(),
                                         {"action": "emotion_bypass"})]
        return updates

    # 根据意图标签路由
    active_agents = set()
    primary_intent = None
    for label in intent_labels:
        intent = label.get("intent", "")
        if label.get("primary"):
            primary_intent = intent
        subgraph = INTENT_TO_SUBGRAPH.get(intent, "general_agent")
        active_agents.add(subgraph)

    if not active_agents:
        active_agents.add("general_agent")

    updates["active_agents"] = list(active_agents)
    updates["routing_reason"] = f"意图路由: {primary_intent or 'unknown'}"
    updates["trace_events"] = [trace(trace_id, "orchestrator_gate", "completed",
                                     timer.elapsed_ms(),
                                     {"action": "normal_routing",
                                      "active_agents": list(active_agents)})]

    return updates


# ==================== 条件边: 路由函数 ====================

def route_by_labels(state: dict) -> list[str]:
    """根据orchestrator_gate的路由决策返回目标节点列表"""
    active_agents = state.get("active_agents", [])

    # 特殊路由: 转人工
    if "escalate_to_human" in active_agents:
        return ["escalate_to_human"]

    # 检查是否有escalate信号
    if state.get("escalate_signal") == "to_human":
        return ["escalate_to_human"]
    if state.get("escalate_signal") == "to_complaint":
        return ["complaint_agent"]

    # 检查澄清重入
    if state.get("pending_clarification"):
        return [state.get("pending_subgraph", "general_agent")]

    return active_agents if active_agents else ["general_agent"]
