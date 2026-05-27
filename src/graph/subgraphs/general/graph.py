"""
通用Agent子图 (最简单 + 降级fallback目标)

节点:
  1. faq_matcher     → FAQ匹配
  2. policy_search   → RAG搜索店铺政策
  3. general_respond → 编译通用回复
  4. emotion_monitor → 情绪监控 (检测升级信号)

特殊职责:
- 当其他子图超时/异常时, supervisor降级到此子图使用预置话术
- emotion_monitor检测到情绪恶化 → 发出escalate_to_complaint信号

输出类型: normal | escalate
"""

import logging

from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool

from src.config.settings import GENERATOR_MODEL, LLM_BASE_URL, EMOTION_INTENSITY_THRESHOLD
from src.state.schema import GeneralState, RESULT_TYPE_NORMAL, ESCALATE_TO_COMPLAINT
from src.utils.observability import TraceTimer, trace

logger = logging.getLogger(__name__)


# ==================== 工具定义 ====================

@tool
def search_faq(query: str) -> dict:
    """搜索FAQ知识库"""
    # Mock实现 - 实际项目中连接FAQ数据库
    faq_db = {
        "退货": {"answer": "自签收之日起7天内可申请退货，商品需保持原包装。", "category": "售后"},
        "运费": {"answer": "订单满99元免运费，否则收取8元运费。", "category": "物流"},
        "支付": {"answer": "支持微信、支付宝、银行卡等多种支付方式。", "category": "支付"},
        "营业时间": {"answer": "在线客服7x24小时服务，电话客服9:00-21:00。", "category": "通用"},
        "保修": {"answer": "电子产品享有1年保修期，配件享有6个月保修。", "category": "售后"},
    }
    for key, value in faq_db.items():
        if key in query:
            return value
    return {"answer": "未找到匹配的FAQ", "category": "unknown"}


@tool
def search_policy(query: str) -> dict:
    """搜索店铺政策"""
    policy_db = {
        "退换货": "7天无理由退换，15天质量问题包换，1年保修。",
        "配送": "全国包邮（偏远地区除外），标准配送2-5天，加急1-2天。",
        "发票": "支持电子发票和纸质发票，下单时备注即可。",
        "会员": "普通会员积分1倍，VIP会员积分2倍，企业会员专属折扣。",
    }
    for key, value in policy_db.items():
        if key in query:
            return {"policy": value, "matched": key}
    return {"policy": "请咨询人工客服获取详细政策信息。", "matched": "none"}


# ==================== 节点函数 ====================

def faq_matcher(state: dict) -> dict:
    """FAQ匹配节点"""
    timer = TraceTimer()
    timer.start()
    trace_id = state.get("trace_id", "")

    messages = state.get("messages", [])
    last_msg = messages[-1].content if messages else ""

    try:
        llm = ChatOpenAI(model=GENERATOR_MODEL, temperature=0, base_url=LLM_BASE_URL).bind_tools([search_faq])
        response = llm.invoke([{"role": "user", "content": last_msg}])
        # 尝试从tool_calls获取结果
        if hasattr(response, "tool_calls") and response.tool_calls:
            for tc in response.tool_calls:
                if tc["name"] == "search_faq":
                    result = search_faq.invoke(tc["args"])
                    return {
                        "faq_result": result,
                        "tool_calls_made": [{"tool": "search_faq", "args": tc["args"], "result": result}],
                        "trace_events": [trace(trace_id, "faq_matcher", "completed", timer.elapsed_ms())],
                    }
    except Exception as e:
        logger.error(f"FAQ匹配失败: {e}")

    return {
        "faq_result": None,
        "trace_events": [trace(trace_id, "faq_matcher", "completed", timer.elapsed_ms(), {"status": "no_match"})],
    }


def policy_search_node(state: dict) -> dict:
    """政策搜索节点"""
    timer = TraceTimer()
    timer.start()
    trace_id = state.get("trace_id", "")

    messages = state.get("messages", [])
    last_msg = messages[-1].content if messages else ""

    try:
        llm = ChatOpenAI(model=GENERATOR_MODEL, temperature=0, base_url=LLM_BASE_URL).bind_tools([search_policy])
        response = llm.invoke([{"role": "user", "content": last_msg}])
        if hasattr(response, "tool_calls") and response.tool_calls:
            for tc in response.tool_calls:
                if tc["name"] == "search_policy":
                    result = search_policy.invoke(tc["args"])
                    return {
                        "policy_result": result,
                        "tool_calls_made": [{"tool": "search_policy", "args": tc["args"], "result": result}],
                        "trace_events": [trace(trace_id, "policy_search", "completed", timer.elapsed_ms())],
                    }
    except Exception as e:
        logger.error(f"政策搜索失败: {e}")

    return {
        "policy_result": None,
        "trace_events": [trace(trace_id, "policy_search", "completed", timer.elapsed_ms(), {"status": "no_match"})],
    }


def general_respond(state: dict) -> dict:
    """编译通用回复"""
    timer = TraceTimer()
    timer.start()
    trace_id = state.get("trace_id", "")

    messages = state.get("messages", [])
    last_msg = messages[-1].content if messages else ""

    faq = state.get("faq_result")
    policy = state.get("policy_result")

    # 构建上下文
    context_parts = []
    if faq and faq.get("answer") != "未找到匹配的FAQ":
        context_parts.append(f"FAQ: {faq['answer']}")
    if policy and policy.get("matched") != "none":
        context_parts.append(f"政策: {policy['policy']}")

    context = "\n".join(context_parts) if context_parts else "未找到相关信息，请用通用方式回复。"

    try:
        llm = ChatOpenAI(model=GENERATOR_MODEL, temperature=0.3, base_url=LLM_BASE_URL)
        prompt = f"""根据以下信息回答客户的问题。
如果FAQ或政策中有相关信息，请使用。
如果没有直接匹配的信息，请友好地告知客户并建议转人工客服。

背景信息:
{context}

客户消息: {last_msg}

请直接回复客户:"""
        response = llm.invoke([{"role": "user", "content": prompt}])
        answer = response.content
    except Exception as e:
        logger.error(f"通用回复生成失败: {e}")
        answer = "感谢您的咨询，我暂时无法回答您的问题。您可以回复'人工客服'获取更多帮助。"

    return {
        "result_type": RESULT_TYPE_NORMAL,
        "findings": {
            "answer": answer,
            "faq_matched": faq is not None and faq.get("answer") != "未找到匹配的FAQ",
            "policy_matched": policy is not None and policy.get("matched") != "none",
        },
        "escalate_signal": None,
        "trace_events": [trace(trace_id, "general_respond", "completed", timer.elapsed_ms())],
    }


def emotion_monitor(state: dict) -> dict:
    """情绪监控节点 - 检测升级信号"""
    timer = TraceTimer()
    timer.start()
    trace_id = state.get("trace_id", "")

    emotion = state.get("emotion", "neutral")
    intensity = state.get("emotion_intensity", 0.3)

    escalate = False
    signal = None

    # 检测极端负面情绪
    if intensity > EMOTION_INTENSITY_THRESHOLD and emotion in ("angry", "frustrated"):
        escalate = True
        signal = ESCALATE_TO_COMPLAINT

    # 检测投诉关键词
    messages = state.get("messages", [])
    if messages:
        last_msg = messages[-1].content if messages else ""
        complaint_keywords = ["投诉", "骗子", "315", "曝光", "举报"]
        if any(kw in last_msg for kw in complaint_keywords):
            escalate = True
            signal = ESCALATE_TO_COMPLAINT

    return {
        "emotion_escalate": escalate,
        "escalate_signal": signal,
        "trace_events": [trace(trace_id, "emotion_monitor", "completed",
                               timer.elapsed_ms(), {"escalate": escalate})],
    }


# ==================== 子图构建 ====================

def build_general_subgraph() -> StateGraph:
    """构建通用Agent子图"""
    graph = StateGraph(GeneralState)

    graph.add_node("faq_matcher", faq_matcher)
    graph.add_node("policy_search", policy_search_node)
    graph.add_node("general_respond", general_respond)
    graph.add_node("emotion_monitor", emotion_monitor)

    graph.set_entry_point("faq_matcher")

    # FAQ匹配和政策搜索可以串行（简单场景）
    graph.add_edge("faq_matcher", "policy_search")
    graph.add_edge("policy_search", "general_respond")
    graph.add_edge("general_respond", "emotion_monitor")
    graph.add_edge("emotion_monitor", END)

    return graph


def compile_general_subgraph():
    """编译通用Agent子图"""
    return build_general_subgraph().compile()
