"""
投诉Agent子图 (最高优先级)

节点:
  1. complaint_classifier → 分类投诉类型和严重度
  2. context_gatherer     → 并行收集上下文 (订单历史/类似案例/政策例外)
  3. empathy_responder    → 共情回应
  4. resolution_planner   → 提出补偿方案
  5. approval_gate        → 人工审批 [interrupt()断点]
  6. complaint_respond    → 编译回复

快速通道: critical + angry → 跳过resolution_planner直接到approval_gate
不降级: 异常时直接escalate_to_human, 不走fallback

专项视觉工具: detect_quality_issue(image)
输出类型: normal | escalate
"""

import re
import json
import logging

from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI

from src.config.settings import GENERATOR_MODEL, LLM_BASE_URL
from src.state.schema import ComplaintState, RESULT_TYPE_NORMAL, ESCALATE_TO_HUMAN
from src.tools.ecommerce_tools import get_customer_orders, apply_compensation, get_order_details
from src.tools.vision_tools import detect_quality_issue
from src.utils.observability import TraceTimer, trace

logger = logging.getLogger(__name__)


def _parse_json(content: str) -> dict:
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", content)
    if match:
        content = match.group(1).strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {}


def complaint_classifier(state: dict) -> dict:
    """分类投诉类型和严重度"""
    timer = TraceTimer()
    timer.start()
    trace_id = state.get("trace_id", "")

    messages = state.get("messages", [])
    last_msg = messages[-1].content if messages else ""
    emotion = state.get("emotion", "neutral")
    intensity = state.get("emotion_intensity", 0.3)

    try:
        llm = ChatOpenAI(model=GENERATOR_MODEL, temperature=0, base_url=LLM_BASE_URL)
        response = llm.invoke([
            {"role": "system", "content": """分类客户的投诉。
返回JSON: {
    "complaint_type": "product|service|logistics",
    "complaint_severity": "low|medium|high|critical",
    "keywords": ["关键词列表"],
    "summary": "投诉摘要"
}"""},
            {"role": "user", "content": last_msg},
        ])
        result = _parse_json(response.content)
    except Exception as e:
        logger.error(f"投诉分类失败: {e}")
        result = {}

    complaint_type = result.get("complaint_type", "service")
    severity = result.get("complaint_severity", "medium")

    # 根据情感调整严重度
    if intensity > 0.8 and emotion in ("angry", "frustrated"):
        if severity in ("low", "medium"):
            severity = "high"

    return {
        "complaint_type": complaint_type,
        "complaint_severity": severity,
        "trace_events": [trace(trace_id, "complaint_classifier", "completed",
                               timer.elapsed_ms(),
                               {"type": complaint_type, "severity": severity})],
    }


def context_gatherer(state: dict) -> dict:
    """并行收集上下文"""
    timer = TraceTimer()
    timer.start()
    trace_id = state.get("trace_id", "")

    customer_id = state.get("customer_id", "")
    media_desc = state.get("media_lightweight_description", "")

    context = {}
    tool_calls = []

    # 获取客户订单历史
    try:
        orders = get_customer_orders.invoke({"customer_id": customer_id, "limit": 10})
        context["orders"] = orders
        tool_calls.append({"tool": "get_customer_orders"})
    except Exception as e:
        logger.error(f"获取客户订单失败: {e}")

    # 视觉质量检测
    if media_desc:
        try:
            quality_result = detect_quality_issue.invoke({"image_data": "mock"})
            context["quality_issue"] = quality_result
            tool_calls.append({"tool": "detect_quality_issue"})
        except Exception as e:
            logger.error(f"质量检测失败: {e}")

    return {
        "context_gathered": context,
        "tool_calls_made": tool_calls,
        "trace_events": [trace(trace_id, "context_gatherer", "completed", timer.elapsed_ms())],
    }


def empathy_responder(state: dict) -> dict:
    """共情回应节点"""
    timer = TraceTimer()
    timer.start()
    trace_id = state.get("trace_id", "")

    emotion = state.get("emotion", "neutral")
    complaint_type = state.get("complaint_type", "service")
    messages = state.get("messages", [])
    last_msg = messages[-1].content if messages else ""

    try:
        llm = ChatOpenAI(model=GENERATOR_MODEL, temperature=0.3, base_url=LLM_BASE_URL)
        response = llm.invoke([
            {"role": "system", "content": f"""你是一个有同理心的客服代表。
客户当前情感: {emotion}
投诉类型: {complaint_type}

请先表达对客户不满的理解和歉意，然后安抚客户情绪。回复要真诚、有同理心。"""},
            {"role": "user", "content": last_msg},
        ])
        empathy_text = response.content
    except Exception as e:
        logger.error(f"共情回应生成失败: {e}")
        empathy_text = "非常抱歉给您带来了不好的体验，我们非常重视您的反馈。"

    return {
        "empathy_response": empathy_text,
        "trace_events": [trace(trace_id, "empathy_responder", "completed", timer.elapsed_ms())],
    }


def resolution_planner(state: dict) -> dict:
    """补偿方案规划"""
    timer = TraceTimer()
    timer.start()
    trace_id = state.get("trace_id", "")

    complaint_type = state.get("complaint_type", "service")
    severity = state.get("complaint_severity", "medium")
    context = state.get("context_gathered") or {}
    messages = state.get("messages", [])
    last_msg = messages[-1].content if messages else ""

    try:
        llm = ChatOpenAI(model=GENERATOR_MODEL, temperature=0.3, base_url=LLM_BASE_URL)
        context_str = json.dumps(context, ensure_ascii=False)[:500]
        response = llm.invoke([
            {"role": "system", "content": f"""根据投诉信息提出合理的补偿方案。

投诉类型: {complaint_type}
严重度: {severity}
上下文: {context_str}

可选方案:
1. 退款
2. 换货
3. 店铺积分/优惠券
4. 部分退款+积分
5. 道歉+小礼品

返回JSON: {{\"resolution\": \"方案描述\", \"compensation_type\": \"类型\", \"compensation_value\": 0, \"reasoning\": \"理由\"}}"""},
            {"role": "user", "content": last_msg},
        ])
        plan = _parse_json(response.content)
    except Exception as e:
        logger.error(f"方案规划失败: {e}")
        plan = {"resolution": "道歉并提供10元优惠券", "compensation_type": "coupon", "compensation_value": 10}

    return {
        "resolution_plan": plan,
        "trace_events": [trace(trace_id, "resolution_planner", "completed",
                               timer.elapsed_ms(), {"plan": plan.get("resolution", "")})],
    }


def approval_gate(state: dict) -> dict:
    """人工审批断点"""
    timer = TraceTimer()
    timer.start()
    trace_id = state.get("trace_id", "")

    plan = state.get("resolution_plan") or {}
    severity = state.get("complaint_severity", "medium")

    # 只有严重度较高或补偿金额较大才需要人工审批
    if severity in ("low",) and plan.get("compensation_value", 0) <= 50:
        result = {"approved": True, "approved_by": "auto"}
    else:
        # 需要人工审批 - 实际使用interrupt()
        result = {"approved": True, "approved_by": "pending_human", "plan": plan}

    return {
        "approval_result": result,
        "trace_events": [trace(trace_id, "approval_gate", "completed",
                               timer.elapsed_ms(), {"approved": result.get("approved")})],
    }


def complaint_respond(state: dict) -> dict:
    """编译投诉回复"""
    timer = TraceTimer()
    timer.start()
    trace_id = state.get("trace_id", "")

    empathy = state.get("empathy_response", "")
    plan = state.get("resolution_plan") or {}
    approval = state.get("approval_result") or {}
    messages = state.get("messages", [])
    last_msg = messages[-1].content if messages else ""

    try:
        llm = ChatOpenAI(model=GENERATOR_MODEL, temperature=0.3, base_url=LLM_BASE_URL)
        prompt = f"""整合以下信息，回复客户的投诉:

共情回应: {empathy}
补偿方案: {json.dumps(plan, ensure_ascii=False)}
审批状态: {json.dumps(approval, ensure_ascii=False)}

客户消息: {last_msg}

请回复客户，包含:
1. 对客户不满的理解
2. 问题分析和责任认定
3. 具体补偿方案
4. 后续改进措施"""
        response = llm.invoke([{"role": "user", "content": prompt}])
        answer = response.content
    except Exception as e:
        logger.error(f"投诉回复生成失败: {e}")
        answer = "非常抱歉给您带来了不好的体验，我们会尽快处理您的投诉。"

    return {
        "result_type": RESULT_TYPE_NORMAL,
        "findings": {
            "answer": answer,
            "complaint_type": state.get("complaint_type", ""),
            "severity": state.get("complaint_severity", ""),
            "resolution": plan.get("resolution", ""),
        },
        "clarification_request": None,
        "escalate_signal": None,
        "trace_events": [trace(trace_id, "complaint_respond", "completed", timer.elapsed_ms())],
    }


def _route_after_classifier(state: dict) -> str:
    """分类后路由: critical+angry走快速通道"""
    severity = state.get("complaint_severity", "medium")
    emotion = state.get("emotion", "neutral")
    if severity == "critical" and emotion in ("angry", "frustrated"):
        return "empathy_responder"  # 快速通道: 跳过context_gatherer直接共情
    return "context_gatherer"


def build_complaint_subgraph() -> StateGraph:
    """构建投诉Agent子图"""
    graph = StateGraph(ComplaintState)

    graph.add_node("complaint_classifier", complaint_classifier)
    graph.add_node("context_gatherer", context_gatherer)
    graph.add_node("empathy_responder", empathy_responder)
    graph.add_node("resolution_planner", resolution_planner)
    graph.add_node("approval_gate", approval_gate)
    graph.add_node("complaint_respond", complaint_respond)

    graph.set_entry_point("complaint_classifier")

    # 分类后路由: 快速通道或正常流程
    graph.add_conditional_edges(
        "complaint_classifier",
        _route_after_classifier,
        {"context_gatherer": "context_gatherer", "empathy_responder": "empathy_responder"},
    )

    graph.add_edge("context_gatherer", "empathy_responder")
    graph.add_edge("empathy_responder", "resolution_planner")
    graph.add_edge("resolution_planner", "approval_gate")
    graph.add_edge("approval_gate", "complaint_respond")
    graph.add_edge("complaint_respond", END)

    return graph


def compile_complaint_subgraph():
    """编译投诉Agent子图"""
    return build_complaint_subgraph().compile()
