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

import json
import re
import logging

from langgraph.graph import StateGraph, END
from langchain_core.tools import tool

from src.config.settings import GENERATOR_MODEL
from src.config.llm import create_llm
from src.state.schema import PreSalesState, SubgraphOutput, RESULT_TYPE_NORMAL, RESULT_TYPE_CLARIFICATION
from src.tools.ecommerce_tools import (
    check_inventory, find_promotions, search_knowledge_base,
    search_products, get_product_details,
)
from src.utils.observability import TraceTimer, trace
from src.utils.conversation import build_conversation_context

logger = logging.getLogger(__name__)


# ==================== 商品名称清洗 ====================

def _clean_product_name(raw: str) -> str:
    """清洗LLM返回的商品名称，去除多余的解释和markdown格式

    LLM可能返回: '您咨询的商品是**经典纯棉圆领T恤**，价格为129元'
    需要提取: '经典纯棉圆领T恤'
    """
    text = raw.strip()
    # 去除 markdown 加粗标记 **...**
    text = re.sub(r'\*{1,2}([^*]+)\*{1,2}', r'\1', text)
    # 尝试提取引号中的内容
    m = re.search(r'["“「]([^"”」]+)["”」]', text)
    if m:
        return m.group(1).strip()
    # 尝试提取 "是" 后面的名词短语（去掉"商品"、"的"等前缀）
    m = re.search(r'(?:商品(?:名称)?(?:是)?|咨询的|询问的|关于)\s*(.+?)(?:[，。,\.]|$)', text)
    if m:
        return m.group(1).strip()
    # 去掉常见前缀
    text = re.sub(r'^(?:您咨询的|商品|产品)(?:名称)?(?:是)?[:：]?\s*', '', text)
    # 去掉末尾的逗号、句号等
    text = re.sub(r'[，。,.！!？?]+$', '', text)
    # 如果仍有多句话，取最短的那句（通常是商品名）
    parts = re.split(r'[，。,]', text)
    parts = [p.strip() for p in parts if p.strip()]
    if parts:
        # 优先选择包含 "T恤/衫/裤/裙/衣/鞋" 等服装关键词的
        clothing_keywords = ['T恤', '衫', '裤', '裙', '衣', '鞋', '夹克', '卫衣', '外套']
        for p in parts:
            if any(kw in p for kw in clothing_keywords):
                return p
        # 否则取最短的
        return min(parts, key=len)
    return text


# ==================== 节点函数 ====================

def product_lookup(state: dict) -> dict:
    """商品识别节点

    处理流程:
    1. 从对话历史中提取商品关键词（支持追问场景）
    2. 调用 search_products 查询数据库获取真实商品数据（SKU、价格等）
    3. 如果找到精确匹配，用数据库数据覆盖 LLM 提取结果
    """
    timer = TraceTimer()
    timer.start()
    trace_id = state.get("trace_id", "")

    messages = state.get("messages", [])
    last_msg = messages[-1].content if messages else ""

    # 构建对话历史上下文（支持追问: "多少钱" → 从上下文推断T恤）
    conversation_context = build_conversation_context(messages)

    # Step 1: LLM 从对话历史中提取商品名称
    product_name = ""
    try:
        llm = create_llm(GENERATOR_MODEL, temperature=0)
        response = llm.invoke([
            {"role": "system", "content": (
                "从客户消息和对话历史中提取客户正在咨询的商品名称。\n"
                "如果当前消息没有明确商品名，结合之前对话中讨论的商品推断。\n"
                "重要：只返回商品名称本身，不要任何解释、标点、markdown格式。\n"
                "例如输入: '多少钱' -> 输出: 经典纯棉圆领T恤\n"
                "例如输入: '经典纯棉圆领T恤 我178' -> 输出: 经典纯棉圆领T恤"
            )},
            *conversation_context,
            {"role": "user", "content": last_msg},
        ])
        product_name = _clean_product_name(response.content)
    except Exception as e:
        logger.error(f"LLM商品名称提取失败: {e}")
        product_name = last_msg

    logger.info(f"[{trace_id}] 提取商品名称: {product_name}")

    # Step 2: 用商品名称查询数据库，获取真实 SKU、价格等
    product_info = {"product_name": product_name, "keywords": [product_name]}
    try:
        db_result = search_products.invoke({"query": product_name})
        products = db_result.get("products", [])

        # 如果精确名没匹配到，尝试用对话中的原始关键词重试
        if not products:
            # 从最近客户消息中提取可能的商品关键词
            for msg in messages[-6:]:
                content = getattr(msg, "content", "")
                if getattr(msg, "type", "") == "human" and content != last_msg:
                    db_result = search_products.invoke({"query": content})
                    products = db_result.get("products", [])
                    if products:
                        logger.info(f"[{trace_id}] 重试匹配成功，使用历史消息: {content[:30]}")
                        break

        if products:
            # 取最佳匹配
            best = products[0]
            product_info = {
                "product_name": best.get("name", product_name),
                "sku": best.get("sku", ""),
                "price": best.get("price", 0),
                "category": best.get("category", ""),
                "color": best.get("color", ""),
                "material": best.get("material", ""),
                "status": best.get("status", ""),
                "keywords": [product_name],
            }
            logger.info(f"[{trace_id}] 数据库匹配成功: sku={product_info['sku']}, "
                        f"name={product_info['product_name']}, price={product_info['price']}")

            # Step 3: 获取详细尺码信息
            if product_info.get("sku"):
                try:
                    details = get_product_details.invoke({"sku": product_info["sku"]})
                    product_info["size_chart"] = details.get("size_chart", [])
                except Exception as e:
                    logger.warning(f"获取尺码详情失败: {e}")
        else:
            logger.warning(f"[{trace_id}] 数据库未找到匹配商品: {product_name}")
    except Exception as e:
        logger.error(f"数据库商品查询失败: {e}")

    return {
        "product_info": product_info,
        "trace_events": [trace(trace_id, "product_lookup", "completed",
                               timer.elapsed_ms(),
                               {"sku": product_info.get("sku", ""),
                                "price": product_info.get("price", 0)})],
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
        llm = create_llm(GENERATOR_MODEL, temperature=0.3)
        prompt = f"""基于以下商品信息生成3个推荐:
商品: {product_info}
库存: {inventory}

返回JSON: {{"recommendations": [{{"name": "...", "reason": "..."}}]}}"""
        response = llm.invoke([{"role": "user", "content": prompt}])
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
        clarification = {
            "question": "请问您想了解哪款商品？可以提供商品名称或链接。",
            "required_info": "product_name",
            "context": {},
        }
        return {
            "agent_findings": [{
                "source_agent": "presales_agent",
                "result_type": RESULT_TYPE_CLARIFICATION,
                "findings": {},
                "clarification_request": clarification,
                "escalate_signal": None,
            }],
            "result_type": RESULT_TYPE_CLARIFICATION,
            "clarification_request": clarification,
            "escalate_signal": None,
            "trace_events": [trace(trace_id, "presales_respond", "completed",
                                   timer.elapsed_ms(), {"action": "clarification"})],
        }

    # 生成回复 — 使用对话历史保持上下文连贯
    try:
        llm = create_llm(GENERATOR_MODEL, temperature=0.3)
        conversation_context = build_conversation_context(messages)

        prompt = f"""根据以下信息回答客户的商品咨询:

商品信息: {product_info}
知识库: {knowledge}
库存: {inventory}
推荐: {recommendations}
优惠: {promotions}

请直接回复客户，包含商品详情、库存状态、推荐和优惠信息。
注意：如果客户的问题是追问（如"多少钱"、"有货吗"），结合之前的对话上下文回答。"""

        response = llm.invoke([
            {"role": "system", "content": prompt},
            *conversation_context,
            {"role": "user", "content": last_msg},
        ])
        answer = response.content
    except Exception as e:
        logger.error(f"售前回复生成失败: {e}")
        answer = "抱歉，暂时无法获取商品信息，请稍后再试。"

    return {
        "agent_findings": [{
            "source_agent": "presales_agent",
            "result_type": RESULT_TYPE_NORMAL,
            "findings": {
                "answer": answer,
                "product": product_info,
                "in_stock": inventory.get("available", False),
                "promotions": promotions,
            },
            "clarification_request": None,
            "escalate_signal": None,
        }],
        "result_type": RESULT_TYPE_NORMAL,
        "clarification_request": None,
        "escalate_signal": None,
        "trace_events": [trace(trace_id, "presales_respond", "completed", timer.elapsed_ms())],
    }


# ==================== 子图构建 ====================

def build_presales_subgraph() -> StateGraph:
    """构建售前Agent子图"""
    graph = StateGraph(PreSalesState, output=SubgraphOutput)

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
