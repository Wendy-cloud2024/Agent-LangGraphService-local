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
from langgraph.types import Send

from src.config.settings import (
    CLASSIFIER_MODEL,
    HUMAN_TRANSFER_PATTERNS,
    EMOTION_INTENSITY_THRESHOLD,
    INTENT_CATEGORIES,
    INTENT_TO_SUBGRAPH,
    HISTORY_WINDOW_ROUNDS,
)
from src.config.prompts import (
    COMBINED_CLASSIFICATION_PROMPT,
    ROUTING_DECISION_PROMPT,
)
from src.config.llm import create_llm
from src.utils.safety import check_sensitive_words, check_image_safety
from src.utils.observability import TraceTimer, trace
from src.utils.parse import parse_json_response
from src.utils.conversation import build_conversation_context

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


# ==================== 记忆配置 ====================
MAX_MESSAGES_WINDOW = 20  # 工作记忆窗口: 保留最近20条消息


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
    # 轮次分隔: 记录当前轮次开始时 agent_findings 的长度
    # 用于 content_merger 等消费者只使用当前轮次的 findings
    # 避免跨轮累积旧数据（operator.add reducer 无法重置）
    # ============================================================
    current_findings = state.get("agent_findings", [])
    updates["_turn_start_idx"] = len(current_findings)

    # ============================================================
    # 轻量模式: 人工拒绝-重分诊
    # 当 human_decision == "reject_reclassify" 时，跳过安全审核/转人工匹配/
    # 多模态/语言检测/摘要压缩等昂贵步骤，仅重做意图分类+情感检测+路由决策。
    # 人工反馈作为额外上下文注入到分类 prompt 中。
    # ============================================================
    if state.get("human_decision") == "reject_reclassify":
        logger.info(f"[{trace_id}] 轻量模式: reject_reclassify, 跳过安全审核, 仅重做意图分类")
        updates["human_decision"] = ""  # 清除标记，避免下次仍走轻量模式

        llm = create_llm(CLASSIFIER_MODEL, temperature=0)
        combined_result = {}
        try:
            categories_str = "\n".join(f"  - {c}" for c in INTENT_CATEGORIES)
            prompt = COMBINED_CLASSIFICATION_PROMPT.format(intent_categories=categories_str)

            # 构建上下文: 人工反馈 + 最近对话
            recent_messages = build_conversation_context(messages, max_rounds=3)
            human_feedback = state.get("human_feedback", "")
            extra_context = ""
            if human_feedback:
                extra_context = f"\n[人工审核员反馈: {human_feedback}]"

            response = llm.invoke([
                {"role": "system", "content": prompt + extra_context},
                *recent_messages,
            ])
            combined_result = parse_json_response(response.content)
        except Exception as e:
            logger.error(f"轻量模式分类失败: {e}")

        intent_labels = combined_result.get("intent_labels", [])
        if not intent_labels:
            intent_labels = [{"intent": "general_faq", "confidence": 0.5, "primary": True}]
        updates["intent_labels"] = intent_labels
        updates["emotion"] = combined_result.get("emotion", "neutral")
        updates["emotion_intensity"] = float(combined_result.get("emotion_intensity", 0.3))
        updates["urgency"] = combined_result.get("urgency", "low")

        # 路由决策
        emotion_val = updates.get("emotion", "neutral")
        intensity_val = updates.get("emotion_intensity", 0.3)
        if intensity_val > EMOTION_INTENSITY_THRESHOLD and emotion_val in ("angry", "frustrated"):
            updates["active_agents"] = ["complaint_agent"]
            updates["routing_reason"] = f"轻量模式-极端情感旁路: {emotion_val}"
        else:
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
            updates["routing_reason"] = f"轻量模式-意图路由: {primary_intent or 'unknown'}"

        updates["trace_events"] = [trace(trace_id, "orchestrator_gate", "completed",
                                         timer.elapsed_ms(),
                                         {"action": "lightweight_reclassify",
                                          "active_agents": updates.get("active_agents", []),
                                          "human_feedback": human_feedback[:100] if human_feedback else ""})]
        return updates

    # ============================================================
    # Layer 1: 工作记忆窗口截断
    # ============================================================
    if len(messages) > MAX_MESSAGES_WINDOW:
        logger.info(f"[{trace_id}] 消息窗口截断: {len(messages)} → {MAX_MESSAGES_WINDOW}")
        updates["messages"] = messages[-MAX_MESSAGES_WINDOW:]

    # ============================================================
    # ⓪ 前置状态检查: 澄清重入
    # ============================================================
    if state.get("pending_clarification"):
        # 恢复澄清前保存的累积状态
        acc = state.get("pending_accumulated_state", {})
        if acc:
            updates["intent_labels"] = acc.get("intent_labels", [])
            updates["emotion"] = acc.get("emotion", "neutral")
            updates["customer_tier"] = acc.get("customer_tier", "standard")
            logger.info(f"[{trace_id}] 恢复澄清前状态: intent={updates.get('intent_labels')}, "
                        f"emotion={updates.get('emotion')}")

        # 清除澄清标记
        updates["pending_clarification"] = False

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
    # ③④⑤⑥⑦ 需要LLM的处理步骤
    # ============================================================
    llm = create_llm(CLASSIFIER_MODEL, temperature=0)

    # ④ 语言检测（规则匹配，不需要LLM）
    updates["language"] = _detect_language(customer_text)

    # ⑤ 对话摘要压缩 (Layer 3 记忆)
    from src.utils.summarizer import summarize_messages
    current_messages = updates.get("messages", messages)
    compressed = summarize_messages(current_messages)
    if len(compressed) != len(current_messages):
        updates["messages"] = compressed
        logger.info(f"[{trace_id}] 对话摘要压缩: {len(current_messages)} → {len(compressed)}")

    # ⑥⑦ 合并: 多维标签分类 + 情感检测（单次LLM调用）
    combined_result = {}
    try:
        categories_str = "\n".join(f"  - {c}" for c in INTENT_CATEGORIES)
        prompt = COMBINED_CLASSIFICATION_PROMPT.format(intent_categories=categories_str)

        # 关键修复: 传入最近对话历史，而不仅是最后一条消息
        # 这样 "多少钱" 会被结合上下文识别为关于之前讨论的T恤的追问
        recent_messages = build_conversation_context(current_messages, max_rounds=3)
        response = llm.invoke([
            {"role": "system", "content": prompt},
            *recent_messages,
        ])
        combined_result = parse_json_response(response.content)
    except Exception as e:
        logger.error(f"合并分类失败: {e}")

    intent_labels = combined_result.get("intent_labels", [])
    if not intent_labels:
        intent_labels = [{"intent": "general_faq", "confidence": 0.5, "primary": True}]
    updates["intent_labels"] = intent_labels

    updates["emotion"] = combined_result.get("emotion", "neutral")
    updates["emotion_intensity"] = float(combined_result.get("emotion_intensity", 0.3))
    updates["urgency"] = combined_result.get("urgency", "low")

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

def route_by_labels(state: dict) -> str | list[Send]:
    """根据orchestrator_gate的路由决策返回目标节点

    路由策略:
      - 特殊路由 (转人工/升级/澄清重入): 始终返回 str, 单目标路由
      - 单子图路由 (95%+ 场景): 返回 str, 通过 path_map 映射到节点
      - 多子图并行: 返回 list[Send], 每个子图携带完整状态副本独立执行

    LangGraph Send API 行为:
      - Send(node_name, arg) 中 arg 成为目标节点的完整输入状态
      - 多个 Send 在同一 superstep 中并行执行
      - 所有并行执行完成后, 通过 operator.add reducer 聚合结果
      - subgraph_output_router 在所有并行子图完成后统一触发一次
    """
    active_agents = state.get("active_agents", [])

    # 特殊路由: 转人工 (始终单路由)
    if "escalate_to_human" in active_agents:
        return "escalate_to_human"

    # 检查是否有escalate信号 (始终单路由)
    if state.get("escalate_signal") == "to_human":
        return "escalate_to_human"
    if state.get("escalate_signal") == "to_complaint":
        return "complaint_agent"

    # 检查澄清重入 (始终单路由)
    if state.get("pending_clarification"):
        return state.get("pending_subgraph", "general_agent")

    # 正常路由
    if not active_agents:
        return "general_agent"

    # 单子图: 直接返回字符串 (走 path_map 映射, 保持现有行为)
    if len(active_agents) == 1:
        return active_agents[0]

    # 多子图并行: 使用 Send API 扇出
    # dict(state) 创建浅拷贝, 各子图独立执行互不干扰
    return [Send(agent, dict(state)) for agent in active_agents]
