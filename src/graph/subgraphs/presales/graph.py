"""
售前Agent子图

节点:
  1. product_lookup       → 识别商品 (支持图片匹配SKU)
  2. knowledge_search     → RAG检索商品信息/尺码指南
  3. inventory_check      → 实时库存查询 (@tool)
  4. recommendation_engine→ 尺码/颜色/搭配推荐
  5. promotion_matcher    → 匹配优惠活动 (@tool)
  6. presales_respond     → 编译售前回复

并行执行: knowledge_search + inventory_check + promotion_matcher (Send API fan-out)
专项视觉工具: visual_product_match(image)

输出类型: normal | clarification (商品不明确时)
"""

import logging

from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool

from src.config.settings import GENERATOR_MODEL
from src.state.schema import PreSalesState, RESULT_TYPE_NORMAL, RESULT_TYPE_CLARIFICATION
from src.tools.ecommerce_tools import check_inventory, find_promotions, search_knowledge_base
from src.tools.vision_tools import visual_product_match
from src.utils.observability import TraceTimer, trace

logger = logging.getLogger(__name__)


# ==================== 节点函数 ====================

def product_lookup(state: dict) -> dict:
    """商品识别节点"""
    timer = TraceTimer()
    timer.start()
    trace_id = state.get("trace_id", "")

    messages = state.get("messages", [])
    last_msg = messages[-1].content if messages else ""
    media_desc = state.get("media_lightweight_description", "")

    product_info = None
    try:
        tools = [visual_product_match]
        if media_desc:
            # 有图片时使用视觉工具匹配SKU
            llm = ChatOpenAI(model=GENERATOR_MODEL, temperature=0).bind_tools(tools)
            response = llm.invoke([
                {"role": "system", "content": "根据图片描述匹配商品SKU。"},
                {"role": "user", "content": f"图片描述: {media_desc}"},
            ])
            if hasattr(response, "tool_calls") and response.tool_calls:
                for tc in response.tool_calls:
                    result = visual_product_match.invoke(tc["args"])
                    product_info = result

        if not product_info:
            # 文本查询
            llm = ChatOpenAI(model=GENERATOR_MODEL, temperature=0)
            response = llm.invoke([
                {"role": "system", "content": "从客户消息中提取商品名称或关键词，返回JSON: {\"product_name\": \"...\", \"keywords\": [...]}"},
                {"role": "user", "content": last_msg},
            ])
            import json, re
            match = re.search(r"```(?:json)?\s*([\s\S]*?)```", response.content)
            content = match.group(1).strip() if match else response.content
            try:
                product_info = json.loads(content)
            except json.JSONDecodeError:
                product_info = {"product_name": last_msg, "keywords": [last_msg]}
    except Exception as e:
        logger.error(f"商品识别失败: {e}")
        product_info = {"product_name": last_msg}

    return {
        "product_info": product_info,
        "trace_events": [trace(trace_id, "product_lookup", "completed", timer.elapsed_ms())],
    }


def knowledge_search_node(state: dict) -> dict:
    """知识库检索节点"""
    timer = TraceTimer()
    timer.start()
    trace_id = state.get("trace_id", "")

    product_info = state.get("product_info", {})
    query = product_info.get("product_name", "") if isinstance(product_info, dict) else str(product_info)

    try:
        result = search_knowledge_base.invoke({"query": query})
    except Exception as e:
        logger.error(f"知识库检索失败: {e}")
        result = {"results": []}

    return {
        "knowledge_results": result.get("results", []),
        "tool_calls_made": [{"tool": "search_knowledge_base", "query": query}],
        "trace_events": [trace(trace_id, "knowledge_search", "completed", timer.elapsed_ms())],
    }


def inventory_check_node(state: dict) -> dict:
    """库存查询节点"""
    timer = TraceTimer()
    timer.start()
    trace_id = state.get("trace_id", "")

    product_info = state.get("product_info", {})
    sku = product_info.get("sku", "") if isinstance(product_info, dict) else ""

    try:
        if sku:
            result = check_inventory.invoke({"sku": sku})
        else:
            result = {"available": False, "message": "未指定SKU"}
    except Exception as e:
        logger.error(f"库存查询失败: {e}")
        result = {"available": False, "message": str(e)}

    return {
        "inventory_result": result,
        "tool_calls_made": [{"tool": "check_inventory", "sku": sku}],
        "trace_events": [trace(trace_id, "inventory_check", "completed", timer.elapsed_ms())],
    }


def recommendation_engine(state: dict) -> dict:
    """推荐节点"""
    timer = TraceTimer()
    timer.start()
    trace_id = state.get("trace_id", "")

    # 基于商品信息和客户画像生成推荐
    product_info = state.get("product_info", {})
    inventory = state.get("inventory_result", {})

    try:
        llm = ChatOpenAI(model=GENERATOR_MODEL, temperature=0.3)
        prompt = f"""基于以下商品信息生成3个推荐:
商品: {product_info}
库存: {inventory}

返回JSON: {{"recommendations": [{{"name": "...", "reason": "..."}}]}}"""
        response = llm.invoke([{"role": "user", "content": prompt}])
        import json, re
        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", response.content)
        content = match.group(1).strip() if match else response.content
        result = json.loads(content)
        recommendations = result.get("recommendations", [])
    except Exception as e:
        logger.error(f"推荐生成失败: {e}")
        recommendations = []

    return {
        "recommendations": recommendations,
        "trace_events": [trace(trace_id, "recommendation_engine", "completed", timer.elapsed_ms())],
    }


def promotion_matcher_node(state: dict) -> dict:
    """优惠匹配节点"""
    timer = TraceTimer()
    timer.start()
    trace_id = state.get("trace_id", "")

    product_info = state.get("product_info", {})
    sku = product_info.get("sku", "") if isinstance(product_info, dict) else ""

    try:
        result = find_promotions.invoke({
            "product_ids": [sku] if sku else [],
            "customer_tier": state.get("customer_tier", "standard"),
        })
    except Exception as e:
        logger.error(f"优惠匹配失败: {e}")
        result = {"promotions": []}

    return {
        "promotions": result.get("promotions", []),
        "tool_calls_made": [{"tool": "find_promotions", "sku": sku}],
        "trace_events": [trace(trace_id, "promotion_matcher", "completed", timer.elapsed_ms())],
    }


def presales_respond(state: dict) -> dict:
    """编译售前回复"""
    timer = TraceTimer()
    timer.start()
    trace_id = state.get("trace_id", "")

    product_info = state.get("product_info", {})
    knowledge = state.get("knowledge_results", [])
    inventory = state.get("inventory_result", {})
    recommendations = state.get("recommendations", [])
    promotions = state.get("promotions", [])
    messages = state.get("messages", [])
    last_msg = messages[-1].content if messages else ""

    # 检查是否需要澄清（商品不明确）
    if not product_info or (isinstance(product_info, dict) and not product_info.get("sku") and not product_info.get("product_name")):
        return {
            "result_type": RESULT_TYPE_CLARIFICATION,
            "clarification_request": {
                "question": "请问您想了解哪款商品？可以提供商品名称或链接。",
                "required_info": "product_name",
                "context": {},
            },
            "findings": {},
            "escalate_signal": None,
            "trace_events": [trace(trace_id, "presales_respond", "completed",
                                   timer.elapsed_ms(), {"action": "clarification"})],
        }

    # 生成回复
    try:
        llm = ChatOpenAI(model=GENERATOR_MODEL, temperature=0.3)
        prompt = f"""根据以下信息回答客户的商品咨询:

商品信息: {product_info}
知识库: {knowledge}
库存: {inventory}
推荐: {recommendations}
优惠: {promotions}

客户消息: {last_msg}

请直接回复客户，包含商品详情、库存状态、推荐和优惠信息。"""
        response = llm.invoke([{"role": "user", "content": prompt}])
        answer = response.content
    except Exception as e:
        logger.error(f"售前回复生成失败: {e}")
        answer = "抱歉，暂时无法获取商品信息，请稍后再试。"

    return {
        "result_type": RESULT_TYPE_NORMAL,
        "findings": {
            "answer": answer,
            "product": product_info,
            "in_stock": inventory.get("available", False),
            "promotions": promotions,
        },
        "clarification_request": None,
        "escalate_signal": None,
        "trace_events": [trace(trace_id, "presales_respond", "completed", timer.elapsed_ms())],
    }


# ==================== 子图构建 ====================

def build_presales_subgraph() -> StateGraph:
    """构建售前Agent子图"""
    graph = StateGraph(PreSalesState)

    graph.add_node("product_lookup", product_lookup)
    graph.add_node("knowledge_search", knowledge_search_node)
    graph.add_node("inventory_check", inventory_check_node)
    graph.add_node("recommendation_engine", recommendation_engine)
    graph.add_node("promotion_matcher", promotion_matcher_node)
    graph.add_node("presales_respond", presales_respond)

    graph.set_entry_point("product_lookup")
    graph.add_edge("product_lookup", "knowledge_search")
    graph.add_edge("knowledge_search", "inventory_check")
    graph.add_edge("inventory_check", "recommendation_engine")
    graph.add_edge("recommendation_engine", "promotion_matcher")
    graph.add_edge("promotion_matcher", "presales_respond")
    graph.add_edge("presales_respond", END)

    return graph


def compile_presales_subgraph():
    """编译售前Agent子图"""
    return build_presales_subgraph().compile()
