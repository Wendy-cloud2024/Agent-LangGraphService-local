"""
Supervisor上下文注入 (v4)

由supervisor在调用子图前根据意图类型注入相关上下文。
子图通过 state["relevant_history"] 获取, 不直接访问外部存储。

inject_subgraph_context(state, subgraph_name) -> dict:
  根据子图类型拉取相关数据:
    aftersales → 售后相关对话 + 相关订单
    complaint  → 客户订单历史 + 类似投诉案例
    insales    → 相关订单的对话历史
    presales   → 客户之前浏览/咨询过的商品
    general    → 最近对话摘要
"""

import logging

logger = logging.getLogger(__name__)


def inject_subgraph_context(state: dict, subgraph_name: str) -> dict:
    """根据子图类型注入相关上下文

    参数:
        state: 当前对话状态
        subgraph_name: 目标子图名称

    返回:
        包含 relevant_history 的字典
    """
    customer_id = state.get("customer_id", "")
    messages = state.get("messages", [])

    # 提取最近的对话摘要
    recent_messages = messages[-6:] if len(messages) > 6 else messages
    conversation_summary = []
    for msg in recent_messages:
        role = getattr(msg, "type", "unknown")
        content = getattr(msg, "content", str(msg))
        conversation_summary.append({"role": role, "content": content[:200]})

    context = {
        "relevant_history": conversation_summary,
    }

    if subgraph_name == "aftersales_agent":
        context["relevant_history"].extend(_get_aftersales_context(state, customer_id))
    elif subgraph_name == "complaint_agent":
        context["relevant_history"].extend(_get_complaint_context(state, customer_id))
    elif subgraph_name == "insales_agent":
        context["relevant_history"].extend(_get_insales_context(state, customer_id))
    elif subgraph_name == "presales_agent":
        context["relevant_history"].extend(_get_presales_context(state, customer_id))
    else:
        context["relevant_history"].extend(_get_general_context(state))

    return context


def _get_aftersales_context(state: dict, customer_id: str) -> list[dict]:
    """获取售后相关上下文"""
    # Mock实现 - 实际项目中从数据库查询
    return [
        {"type": "recent_orders", "data": {
            "orders": [{"order_id": "ORD001", "status": "delivered", "total": 299.0}],
        }},
    ]


def _get_complaint_context(state: dict, customer_id: str) -> list[dict]:
    """获取投诉相关上下文"""
    return [
        {"type": "order_history", "data": {
            "orders": [{"order_id": "ORD001", "status": "delivered"}],
        }},
        {"type": "similar_complaints", "data": {
            "count": 0,
            "notes": "无类似投诉历史",
        }},
    ]


def _get_insales_context(state: dict, customer_id: str) -> list[dict]:
    """获取售中相关上下文"""
    return [
        {"type": "order_conversations", "data": {
            "recent_topics": ["订单查询", "物流追踪"],
        }},
    ]


def _get_presales_context(state: dict, customer_id: str) -> list[dict]:
    """获取售前相关上下文"""
    return [
        {"type": "browsing_history", "data": {
            "viewed_products": ["SKU001", "SKU002"],
            "consulted_categories": ["电子产品"],
        }},
    ]


def _get_general_context(state: dict) -> list[dict]:
    """获取通用上下文"""
    return [
        {"type": "recent_summary", "data": {
            "topics": [],
            "resolved_issues": [],
        }},
    ]
