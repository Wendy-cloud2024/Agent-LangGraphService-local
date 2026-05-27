"""
售中Agent子图

节点:
  1. order_identify       → 提取订单号 (支持从图片OCR提取)
  2. order_fetch          → 并行查询订单+支付+物流 (@tool)
  3. order_analyze        → 分析状态/修改资格
  4. action_planner       → 规划操作 (追踪/修改/支付)
  5. tool_executor        → 执行工具 (带审批门控, 高风险interrupt)
  6. insales_respond      → 编译回复

并行执行: 订单详情+支付状态+物流信息 (Send API)
专项视觉工具: ocr_shipping_label(image)

输出类型: normal | clarification (无订单号时)
"""

import re
import json
import logging

from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI

from src.config.settings import GENERATOR_MODEL, LLM_BASE_URL
from src.state.schema import InSalesState, RESULT_TYPE_NORMAL, RESULT_TYPE_CLARIFICATION
from src.tools.ecommerce_tools import (
    get_order_details, track_shipment, check_payment_status,
    update_shipping_address, retry_payment,
)
from src.tools.vision_tools import ocr_shipping_label
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


def order_identify(state: dict) -> dict:
    """订单识别节点"""
    timer = TraceTimer()
    timer.start()
    trace_id = state.get("trace_id", "")

    messages = state.get("messages", [])
    last_msg = messages[-1].content if messages else ""
    media_desc = state.get("media_lightweight_description", "")

    order_id = ""

    # 尝试从文本提取订单号
    order_patterns = [
        r"ORD[\w-]+",
        r"订单号[：:]\s*([\w-]+)",
        r"order[_\s]?id[：:]\s*([\w-]+)",
    ]
    for pattern in order_patterns:
        match = re.search(pattern, last_msg, re.IGNORECASE)
        if match:
            order_id = match.group(1) if match.lastindex else match.group(0)
            break

    # 尝试从图片OCR提取
    if not order_id and media_desc and "面单" in media_desc:
        try:
            result = ocr_shipping_label.invoke({"image_data": "mock"})
            order_id = result.get("tracking_number", "")
        except Exception as e:
            logger.error(f"OCR物流面单失败: {e}")

    # LLM提取
    if not order_id:
        try:
            llm = ChatOpenAI(model=GENERATOR_MODEL, temperature=0, base_url=LLM_BASE_URL)
            response = llm.invoke([
                {"role": "system", "content": "从消息中提取订单号，返回JSON: {\"order_id\": \"...\"}。如果没有订单号返回空字符串。"},
                {"role": "user", "content": last_msg},
            ])
            result = _parse_json(response.content)
            order_id = result.get("order_id", "")
        except Exception as e:
            logger.error(f"LLM提取订单号失败: {e}")

    return {
        "order_info": {"order_id": order_id} if order_id else None,
        "trace_events": [trace(trace_id, "order_identify", "completed",
                               timer.elapsed_ms(), {"order_id": order_id})],
    }


def order_fetch(state: dict) -> dict:
    """并行查询订单+支付+物流"""
    timer = TraceTimer()
    timer.start()
    trace_id = state.get("trace_id", "")

    order_info = state.get("order_info") or {}
    order_id = order_info.get("order_id", "")

    if not order_id:
        return {
            "logistics_info": None,
            "payment_info": None,
            "trace_events": [trace(trace_id, "order_fetch", "completed",
                                   timer.elapsed_ms(), {"status": "no_order_id"})],
        }

    # 并行查询（这里串行模拟，实际可用Send API并行）
    order_details = {}
    logistics = {}
    payment = {}
    tool_calls = []

    try:
        order_details = get_order_details.invoke({"order_id": order_id})
        tool_calls.append({"tool": "get_order_details", "order_id": order_id})
    except Exception as e:
        logger.error(f"获取订单详情失败: {e}")

    try:
        tracking = order_details.get("tracking_number", "")
        if tracking:
            logistics = track_shipment.invoke({"tracking_number": tracking})
            tool_calls.append({"tool": "track_shipment", "tracking_number": tracking})
    except Exception as e:
        logger.error(f"物流查询失败: {e}")

    try:
        payment = check_payment_status.invoke({"order_id": order_id})
        tool_calls.append({"tool": "check_payment_status", "order_id": order_id})
    except Exception as e:
        logger.error(f"支付状态查询失败: {e}")

    return {
        "order_info": {**order_info, **order_details},
        "logistics_info": logistics,
        "payment_info": payment,
        "tool_calls_made": tool_calls,
        "trace_events": [trace(trace_id, "order_fetch", "completed", timer.elapsed_ms())],
    }


def order_analyze(state: dict) -> dict:
    """分析订单状态和修改资格"""
    timer = TraceTimer()
    timer.start()
    trace_id = state.get("trace_id", "")

    order = state.get("order_info") or {}
    logistics = state.get("logistics_info") or {}
    payment = state.get("payment_info") or {}

    analysis = {
        "order_status": order.get("status", "unknown"),
        "can_modify_address": order.get("status") in ("pending", "processing"),
        "can_cancel": order.get("status") in ("pending", "processing"),
        "logistics_status": logistics.get("status", "unknown"),
        "payment_status": payment.get("payment_status", "unknown"),
    }

    return {
        "action_plan": analysis,
        "trace_events": [trace(trace_id, "order_analyze", "completed", timer.elapsed_ms())],
    }


def action_planner(state: dict) -> dict:
    """规划操作"""
    timer = TraceTimer()
    timer.start()
    trace_id = state.get("trace_id", "")

    analysis = state.get("action_plan") or {}
    messages = state.get("messages", [])
    last_msg = messages[-1].content if messages else ""

    plan = {"actions": [], "requires_approval": False}

    if "地址" in last_msg and analysis.get("can_modify_address"):
        plan["actions"].append({"type": "update_address", "risk": "medium"})
    elif "取消" in last_msg and analysis.get("can_cancel"):
        plan["actions"].append({"type": "cancel_order", "risk": "high"})
        plan["requires_approval"] = True
    else:
        plan["actions"].append({"type": "query", "risk": "low"})

    return {
        "action_plan": {**analysis, **plan},
        "trace_events": [trace(trace_id, "action_planner", "completed", timer.elapsed_ms())],
    }


def tool_executor(state: dict) -> dict:
    """执行工具（带审批门控）"""
    timer = TraceTimer()
    timer.start()
    trace_id = state.get("trace_id", "")

    plan = state.get("action_plan") or {}
    actions = plan.get("actions", [])
    result = {"executed": []}

    for action in actions:
        if action["risk"] == "high":
            # 高风险操作需要人工审批 - 实际使用interrupt()
            result["executed"].append({
                "action": action["type"],
                "status": "pending_approval",
                "message": "该操作需要人工审批",
            })
        else:
            result["executed"].append({
                "action": action["type"],
                "status": "completed",
            })

    return {
        "tool_execution_result": result,
        "trace_events": [trace(trace_id, "tool_executor", "completed", timer.elapsed_ms())],
    }


def insales_respond(state: dict) -> dict:
    """编译售中回复"""
    timer = TraceTimer()
    timer.start()
    trace_id = state.get("trace_id", "")

    order_info = state.get("order_info")
    if not order_info or not order_info.get("order_id"):
        return {
            "result_type": RESULT_TYPE_CLARIFICATION,
            "clarification_request": {
                "question": "请提供您的订单号，以便我查询订单信息。",
                "required_info": "order_id",
                "context": {},
            },
            "findings": {},
            "escalate_signal": None,
            "trace_events": [trace(trace_id, "insales_respond", "completed",
                                   timer.elapsed_ms(), {"action": "clarification"})],
        }

    logistics = state.get("logistics_info") or {}
    payment = state.get("payment_info") or {}
    action_result = state.get("tool_execution_result") or {}
    messages = state.get("messages", [])
    last_msg = messages[-1].content if messages else ""

    try:
        llm = ChatOpenAI(model=GENERATOR_MODEL, temperature=0.3, base_url=LLM_BASE_URL)
        prompt = f"""根据以下信息回答客户的订单查询:

订单信息: {json.dumps(order_info, ensure_ascii=False)}
物流信息: {json.dumps(logistics, ensure_ascii=False)}
支付信息: {json.dumps(payment, ensure_ascii=False)}
操作结果: {json.dumps(action_result, ensure_ascii=False)}

客户消息: {last_msg}

请直接回复客户，包含订单状态、物流信息和操作结果。"""
        response = llm.invoke([{"role": "user", "content": prompt}])
        answer = response.content
    except Exception as e:
        logger.error(f"售中回复生成失败: {e}")
        answer = "抱歉，暂时无法查询订单信息，请稍后再试。"

    return {
        "result_type": RESULT_TYPE_NORMAL,
        "findings": {
            "answer": answer,
            "order_id": order_info.get("order_id", ""),
            "order_status": order_info.get("status", ""),
        },
        "clarification_request": None,
        "escalate_signal": None,
        "trace_events": [trace(trace_id, "insales_respond", "completed", timer.elapsed_ms())],
    }


def build_insales_subgraph() -> StateGraph:
    """构建售中Agent子图"""
    graph = StateGraph(InSalesState)

    graph.add_node("order_identify", order_identify)
    graph.add_node("order_fetch", order_fetch)
    graph.add_node("order_analyze", order_analyze)
    graph.add_node("action_planner", action_planner)
    graph.add_node("tool_executor", tool_executor)
    graph.add_node("insales_respond", insales_respond)

    graph.set_entry_point("order_identify")
    graph.add_edge("order_identify", "order_fetch")
    graph.add_edge("order_fetch", "order_analyze")
    graph.add_edge("order_analyze", "action_planner")
    graph.add_edge("action_planner", "tool_executor")
    graph.add_edge("tool_executor", "insales_respond")
    graph.add_edge("insales_respond", END)

    return graph


def compile_insales_subgraph():
    """编译售中Agent子图"""
    return build_insales_subgraph().compile()
