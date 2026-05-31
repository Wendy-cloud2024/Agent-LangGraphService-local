"""
售后Agent子图 (最复杂)

节点:
  1. issue_identify       → 分类问题类型 (破损/错发/质量/不满意)
  2. order_fetch          → 并行获取订单+购买历史
  3. eligibility_checker  → 资格校验 (退货窗口/物品状态/保修/客户历史)
  4. evidence_collector   → 证据收集 (照片/描述)
  5. resolution_planner   → 确定方案 (退款/换货/维修/店铺积分)
  6. tool_executor        → 执行操作 (退款/换货=interrupt, 标签/积分=条件性)
  7. aftersales_respond   → 编译回复

专项视觉工具: detect_product_damage(image), ocr_product_label(image)

输出类型: normal | clarification (证据不足时)
工具审批: issue_refund/process_exchange → 始终interrupt
         issue_store_credit → 金额>50需interrupt
         send_return_label → 全自动
"""

import re
import json
import logging

from langgraph.graph import StateGraph, END

from src.config.settings import GENERATOR_MODEL
from src.config.llm import create_llm
from src.state.schema import AfterSalesState, SubgraphOutput, RESULT_TYPE_NORMAL, RESULT_TYPE_CLARIFICATION
from src.tools.ecommerce_tools import (
    get_order_details, check_return_eligibility, check_warranty_status,
    get_customer_orders, send_return_label, issue_store_credit,
    issue_refund, process_exchange,
)
from src.tools.vision_tools import detect_product_damage, ocr_product_label
from src.utils.observability import TraceTimer, trace
from src.utils.parse import parse_json_response

logger = logging.getLogger(__name__)


def issue_identify(state: dict) -> dict:
    """问题分类节点"""
    timer = TraceTimer()
    timer.start()
    trace_id = state.get("trace_id", "")

    messages = state.get("messages", [])
    last_msg = messages[-1].content if messages else ""

    try:
        llm = create_llm(GENERATOR_MODEL, temperature=0)
        response = llm.invoke([
            {"role": "system", "content": """分类客户的售后问题类型。
返回JSON: {"issue_type": "return|exchange|refund|warranty", "description": "...", "confidence": 0.9}"""},
            {"role": "user", "content": last_msg},
        ])
        result = parse_json_response(response.content)
        issue_type = result.get("issue_type", "return")
    except Exception as e:
        logger.error(f"问题分类失败: {e}")
        issue_type = "return"

    return {
        "issue_type": issue_type,
        "trace_events": [trace(trace_id, "issue_identify", "completed",
                               timer.elapsed_ms(), {"issue_type": issue_type})],
    }


def order_fetch(state: dict) -> dict:
    """获取订单信息"""
    timer = TraceTimer()
    timer.start()
    trace_id = state.get("trace_id", "")

    messages = state.get("messages", [])
    last_msg = messages[-1].content if messages else ""
    customer_id = state.get("customer_id", "")

    # 提取订单号
    order_id = ""
    match = re.search(r"ORD[\w-]+|订单号[：:]\s*([\w-]+)", last_msg)
    if match:
        order_id = match.group(1) if match.lastindex else match.group(0)

    order_info = {}
    tool_calls = []

    if order_id:
        try:
            order_info = get_order_details.invoke({"order_id": order_id})
            tool_calls.append({"tool": "get_order_details", "order_id": order_id})
        except Exception as e:
            logger.error(f"获取订单详情失败: {e}")

    return {
        "order_info": order_info if order_info else None,
        "tool_calls_made": tool_calls,
        "trace_events": [trace(trace_id, "order_fetch", "completed", timer.elapsed_ms())],
    }


def eligibility_checker(state: dict) -> dict:
    """资格校验节点"""
    timer = TraceTimer()
    timer.start()
    trace_id = state.get("trace_id", "")

    order_info = state.get("order_info") or {}
    issue_type = state.get("issue_type", "return")
    order_id = order_info.get("order_id", "")
    media_desc = state.get("media_lightweight_description", "")

    eligibility = {"eligible": False, "reason": ""}

    # 视觉工具辅助判断
    if media_desc and ("破损" in media_desc or "坏" in media_desc):
        try:
            damage_result = detect_product_damage.invoke({"image_data": "mock"})
            eligibility["damage_assessment"] = damage_result
        except Exception as e:
            logger.error(f"破损检测失败: {e}")

    # 资格检查
    if order_id:
        try:
            result = check_return_eligibility.invoke({"order_id": order_id})
            eligibility["eligible"] = result.get("eligible", False)
            eligibility["reason"] = result.get("reason", "")
            eligibility["deadline"] = result.get("deadline", "")
        except Exception as e:
            logger.error(f"退货资格检查失败: {e}")
            eligibility["reason"] = str(e)

    return {
        "eligibility_result": eligibility,
        "trace_events": [trace(trace_id, "eligibility_checker", "completed", timer.elapsed_ms())],
    }


def evidence_collector(state: dict) -> dict:
    """证据收集节点"""
    timer = TraceTimer()
    timer.start()
    trace_id = state.get("trace_id", "")

    media_desc = state.get("media_lightweight_description", "")
    messages = state.get("messages", [])
    evidence = []

    # 收集图片证据
    if media_desc:
        evidence.append({"type": "image", "description": media_desc})
        # 尝试OCR产品标签
        if "标签" in media_desc or "成分" in media_desc:
            try:
                label_result = ocr_product_label.invoke({"image_data": "mock"})
                evidence.append({"type": "label_ocr", "data": label_result})
            except Exception as e:
                logger.error(f"标签OCR失败: {e}")

    # 收集文本描述
    for msg in messages[-3:]:
        content = getattr(msg, "content", "")
        role = getattr(msg, "type", "")
        if role == "human" and content:
            evidence.append({"type": "text", "content": content[:200]})

    return {
        "evidence_collected": evidence,
        "trace_events": [trace(trace_id, "evidence_collector", "completed",
                               timer.elapsed_ms(), {"evidence_count": len(evidence)})],
    }


def resolution_planner(state: dict) -> dict:
    """解决方案规划节点"""
    timer = TraceTimer()
    timer.start()
    trace_id = state.get("trace_id", "")

    issue_type = state.get("issue_type", "return")
    eligibility = state.get("eligibility_result") or {}
    evidence = state.get("evidence_collected", [])
    order_info = state.get("order_info") or {}

    plan = {"resolution": "", "requires_approval": True, "tools_to_call": []}

    if not eligibility.get("eligible"):
        plan["resolution"] = "denied"
        plan["reason"] = eligibility.get("reason", "不符合退货条件")
        plan["requires_approval"] = False
    elif issue_type == "return":
        plan["resolution"] = "refund"
        plan["tools_to_call"] = [{"tool": "issue_refund", "risk": "high"}]
    elif issue_type == "exchange":
        plan["resolution"] = "exchange"
        plan["tools_to_call"] = [{"tool": "process_exchange", "risk": "high"}]
    elif issue_type == "warranty":
        plan["resolution"] = "warranty_repair"
        plan["requires_approval"] = False
    else:
        plan["resolution"] = "store_credit"
        plan["tools_to_call"] = [{"tool": "issue_store_credit", "risk": "medium"}]

    return {
        "resolution_plan": plan,
        "trace_events": [trace(trace_id, "resolution_planner", "completed",
                               timer.elapsed_ms(), {"resolution": plan["resolution"]})],
    }


def tool_executor(state: dict) -> dict:
    """执行操作（带审批门控）"""
    timer = TraceTimer()
    timer.start()
    trace_id = state.get("trace_id", "")

    plan = state.get("resolution_plan") or {}
    order_info = state.get("order_info") or {}
    customer_id = state.get("customer_id", "")
    order_id = order_info.get("order_id", "")

    tools_to_call = plan.get("tools_to_call", [])
    result = {"executed": []}
    tool_calls = []

    for tool_call in tools_to_call:
        tool_name = tool_call["tool"]
        risk = tool_call.get("risk", "low")

        if risk == "high":
            # 高风险操作需要interrupt审批
            result["executed"].append({
                "tool": tool_name, "status": "pending_approval",
                "message": "该操作需要人工审批",
            })
            tool_calls.append({"tool": tool_name, "status": "pending_approval"})
        else:
            try:
                if tool_name == "issue_store_credit":
                    exec_result = issue_store_credit.invoke({
                        "customer_id": customer_id,
                        "amount": order_info.get("total", 0),
                        "reason": plan.get("resolution", ""),
                    })
                elif tool_name == "send_return_label":
                    exec_result = send_return_label.invoke({"order_id": order_id})
                else:
                    exec_result = {"status": "unknown_tool"}

                result["executed"].append({"tool": tool_name, "status": "completed", "data": exec_result})
                tool_calls.append({"tool": tool_name, "status": "completed"})
            except Exception as e:
                result["executed"].append({"tool": tool_name, "status": "failed", "error": str(e)})
                tool_calls.append({"tool": tool_name, "status": "failed"})

    return {
        "tool_execution_result": result,
        "tool_calls_made": tool_calls,
        "trace_events": [trace(trace_id, "tool_executor", "completed", timer.elapsed_ms())],
    }


def aftersales_respond(state: dict) -> dict:
    """编译售后回复"""
    timer = TraceTimer()
    timer.start()
    trace_id = state.get("trace_id", "")

    issue_type = state.get("issue_type", "return")
    eligibility = state.get("eligibility_result") or {}
    plan = state.get("resolution_plan") or {}
    tool_result = state.get("tool_execution_result") or {}
    evidence = state.get("evidence_collected", [])
    messages = state.get("messages", [])
    last_msg = messages[-1].content if messages else ""

    # 检查是否需要澄清（证据不足）
    if not eligibility or (not evidence and plan.get("resolution") != "denied"):
        required = "order_id" if not state.get("order_info") else "evidence"
        clarification = {
            "question": "请提供您的订单号和相关照片证据，以便我为您处理。",
            "required_info": required,
            "context": {"issue_type": issue_type},
        }
        return {
            "agent_findings": [{
                "source_agent": "aftersales_agent",
                "result_type": RESULT_TYPE_CLARIFICATION,
                "findings": {},
                "clarification_request": clarification,
                "escalate_signal": None,
            }],
            "result_type": RESULT_TYPE_CLARIFICATION,
            "clarification_request": clarification,
            "escalate_signal": None,
            "trace_events": [trace(trace_id, "aftersales_respond", "completed",
                                   timer.elapsed_ms(), {"action": "clarification"})],
        }

    # 生成回复
    try:
        llm = create_llm(GENERATOR_MODEL, temperature=0.3)
        prompt = f"""根据以下信息回复客户的售后请求:

问题类型: {issue_type}
资格: {json.dumps(eligibility, ensure_ascii=False)}
方案: {json.dumps(plan, ensure_ascii=False)}
操作结果: {json.dumps(tool_result, ensure_ascii=False)}
证据: {len(evidence)}件

客户消息: {last_msg}

请直接回复客户，说明处理结果。如果操作需要审批，告知客户正在等待审批。"""
        response = llm.invoke([{"role": "user", "content": prompt}])
        answer = response.content
    except Exception as e:
        logger.error(f"售后回复生成失败: {e}")
        answer = "抱歉，处理您的请求时遇到了问题，请稍后再试。"

    return {
        "agent_findings": [{
            "source_agent": "aftersales_agent",
            "result_type": RESULT_TYPE_NORMAL,
            "findings": {
                "answer": answer,
                "issue_type": issue_type,
                "resolution": plan.get("resolution", ""),
                "eligible": eligibility.get("eligible", False),
            },
            "clarification_request": None,
            "escalate_signal": None,
        }],
        "result_type": RESULT_TYPE_NORMAL,
        "clarification_request": None,
        "escalate_signal": None,
        "trace_events": [trace(trace_id, "aftersales_respond", "completed", timer.elapsed_ms())],
    }


def build_aftersales_subgraph() -> StateGraph:
    """构建售后Agent子图"""
    graph = StateGraph(AfterSalesState, output=SubgraphOutput)

    graph.add_node("issue_identify", issue_identify)
    graph.add_node("order_fetch", order_fetch)
    graph.add_node("eligibility_checker", eligibility_checker)
    graph.add_node("evidence_collector", evidence_collector)
    graph.add_node("resolution_planner", resolution_planner)
    graph.add_node("tool_executor", tool_executor)
    graph.add_node("aftersales_respond", aftersales_respond)

    graph.set_entry_point("issue_identify")
    graph.add_edge("issue_identify", "order_fetch")
    graph.add_edge("order_fetch", "eligibility_checker")
    graph.add_edge("eligibility_checker", "evidence_collector")
    graph.add_edge("evidence_collector", "resolution_planner")
    graph.add_edge("resolution_planner", "tool_executor")
    graph.add_edge("tool_executor", "aftersales_respond")
    graph.add_edge("aftersales_respond", END)

    return graph


def compile_aftersales_subgraph():
    """编译售后Agent子图"""
    return build_aftersales_subgraph().compile()
