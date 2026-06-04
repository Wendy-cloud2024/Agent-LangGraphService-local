"""
电商后端工具集 (@tool装饰函数)

数据来源: SQLite 数据库 (data/ecommerce.db)
包含: 商品、商品详情/尺码、客户、订单 4张表

工具按风险等级分类:
  低风险 (全自动): 商品查询、库存、订单查询、物流、知识库检索
  中风险 (条件性interrupt): 修改地址、退货标签、积分
  高风险 (始终interrupt): 退款、取消、换货
"""

import logging
from langchain_core.tools import tool

logger = logging.getLogger(__name__)


# ==================== 低风险工具 (全自动) ====================

@tool
def check_inventory(sku: str, region: str = "default") -> dict:
    """查询商品库存"""
    try:
        from src.db.queries import get_product
        product = get_product(sku)
        if not product:
            return {"sku": sku, "available": False, "message": f"商品 {sku} 不存在"}
        return {
            "sku": sku,
            "name": product["name"],
            "region": region,
            "available": True,
            "quantity": 50,  # 简化: 统一返回有库存
            "warehouse": "华东仓",
        }
    except Exception as e:
        logger.error("库存查询失败: %s", e)
        return {"sku": sku, "available": False, "message": str(e)}


@tool
def get_order_details(order_id: str) -> dict:
    """获取订单详情"""
    try:
        from src.db.queries import get_order
        order = get_order(order_id)
        if not order:
            return {"error": f"订单 {order_id} 不存在"}
        return {
            "order_id": order["order_id"],
            "status": order["status"],
            "customer_id": order["customer_id"],
            "items": [{
                "sku": order["sku"],
                "name": order["product_name"],
                "size": order["size"],
                "quantity": order["quantity"],
                "price": order["total_price"],
            }],
            "total": order["total_price"],
            "created_at": order["created_at"],
            "tracking_number": order.get("tracking_number", ""),
        }
    except Exception as e:
        logger.error("订单查询失败: %s", e)
        return {"error": str(e)}


@tool
def track_shipment(tracking_number: str) -> dict:
    """物流追踪"""
    try:
        from src.db.queries import get_tracking
        return get_tracking(tracking_number)
    except Exception as e:
        logger.error("物流查询失败: %s", e)
        return {"tracking_number": tracking_number, "error": str(e)}


@tool
def check_payment_status(order_id: str) -> dict:
    """查询支付状态"""
    try:
        from src.db.queries import get_order
        order = get_order(order_id)
        if not order:
            return {"error": f"订单 {order_id} 不存在"}
        return {
            "order_id": order_id,
            "payment_status": "paid" if order["status"] in ("paid", "shipped", "delivered") else "unpaid",
            "amount": order["total_price"],
        }
    except Exception as e:
        logger.error("支付状态查询失败: %s", e)
        return {"error": str(e)}


@tool
def search_knowledge_base(query: str) -> dict:
    """搜索知识库（RAG 混合检索：向量 + BM25 + RRF 融合）"""
    try:
        from src.rag import get_rag_retriever
        retriever = get_rag_retriever()
        results = retriever.retrieve(query, top_k=5)
        return {
            "query": query,
            "results": [
                {
                    "title": doc.metadata.get("source", ""),
                    "content": doc.content,
                    "relevance": round(score, 4),
                }
                for doc, score in results
            ],
        }
    except Exception as e:
        logger.error("RAG 知识库检索失败: %s", e)
        return {"query": query, "results": []}


@tool
def search_products(query: str) -> dict:
    """搜索商品（按名称/类别/颜色/材质关键词）"""
    try:
        from src.db.queries import search_products as db_search
        results = db_search(query)
        return {"query": query, "products": results, "count": len(results)}
    except Exception as e:
        logger.error("商品搜索失败: %s", e)
        return {"query": query, "products": [], "error": str(e)}


@tool
def get_product_details(sku: str) -> dict:
    """获取商品详情和所有尺码数据"""
    try:
        from src.db.queries import get_product, get_product_all_details
        product = get_product(sku)
        if not product:
            return {"error": f"商品 {sku} 不存在"}
        sizes = get_product_all_details(sku)
        return {
            "product": product,
            "size_chart": sizes,
            "size_count": len(sizes),
        }
    except Exception as e:
        logger.error("商品详情查询失败: %s", e)
        return {"error": str(e)}


@tool
def recommend_size(sku: str, height: float, weight: float) -> dict:
    """根据身高体重推荐尺码"""
    try:
        from src.db.queries import get_size_recommendation, get_product
        product = get_product(sku)
        if not product:
            return {"error": f"商品 {sku} 不存在"}
        result = get_size_recommendation(sku, height, weight)
        if result:
            result["product_name"] = product["name"]
            return result
        return {"error": "无法推荐尺码，请参考尺码表"}
    except Exception as e:
        logger.error("尺码推荐失败: %s", e)
        return {"error": str(e)}


@tool
def check_return_eligibility(order_id: str, item_id: str = "") -> dict:
    """检查退货资格"""
    try:
        from src.db.queries import get_order
        order = get_order(order_id)
        if not order:
            return {"order_id": order_id, "eligible": False, "reason": "订单不存在"}
        status = order["status"]
        if status in ("cancelled", "refunded"):
            return {"order_id": order_id, "eligible": False, "reason": f"订单已{status}"}
        return {
            "order_id": order_id,
            "eligible": True,
            "reason": "符合退货条件",
            "product_name": order["product_name"],
            "size": order["size"],
            "conditions": ["商品需保持原包装", "吊牌完整", "未穿着洗涤"],
        }
    except Exception as e:
        logger.error("退货资格检查失败: %s", e)
        return {"order_id": order_id, "eligible": False, "reason": str(e)}


@tool
def get_customer_orders(customer_id: str, limit: int = 5) -> dict:
    """获取客户订单列表"""
    try:
        from src.db.queries import get_customer_orders as db_get_orders
        orders = db_get_orders(customer_id, limit)
        return {
            "customer_id": customer_id,
            "orders": orders,
            "total_count": len(orders),
        }
    except Exception as e:
        logger.error("客户订单查询失败: %s", e)
        return {"customer_id": customer_id, "orders": [], "error": str(e)}


@tool
def get_customer_info(customer_id: str) -> dict:
    """获取客户信息（含身高体重）"""
    try:
        from src.db.queries import get_customer
        customer = get_customer(customer_id)
        if not customer:
            return {"error": f"客户 {customer_id} 不存在"}
        return customer
    except Exception as e:
        logger.error("客户信息查询失败: %s", e)
        return {"error": str(e)}


@tool
def check_warranty_status(product_id: str, purchase_date: str) -> dict:
    """检查保修状态"""
    # 服装保修简化: 3个月质保
    return {
        "product_id": product_id,
        "warranty_status": "active",
        "expiry_date": "2024-04-15",
        "warranty_type": "服装3个月质保",
    }


@tool
def find_promotions(product_ids: list[str], customer_tier: str = "standard") -> dict:
    """查找可用优惠"""
    promos = [{"name": "满200减20", "discount": 20, "code": "SAVE20"}]
    return {"promotions": promos}


# ==================== 中风险工具 (条件性interrupt) ====================

@tool
def update_shipping_address(order_id: str, new_address: str) -> dict:
    """修改收货地址（金额>200或跨国需审批）"""
    return {
        "order_id": order_id,
        "updated": True,
        "new_address": new_address,
        "requires_approval": False,
    }


@tool
def send_return_label(order_id: str, item_id: str = "") -> dict:
    """发送退货标签"""
    return {
        "order_id": order_id,
        "label_url": f"https://example.com/return-label/{order_id}",
        "tracking_number": f"RT{order_id[-3:]}123456",
        "instructions": "请打印退货标签并贴在包裹上，前往最近的快递点寄回。",
    }


@tool
def issue_store_credit(customer_id: str, amount: float, reason: str) -> dict:
    """发放店铺积分（金额>50需审批）"""
    return {
        "customer_id": customer_id,
        "amount": amount,
        "reason": reason,
        "credit_id": f"CRT-{customer_id}",
        "issued": True,
    }


@tool
def retry_payment(order_id: str) -> dict:
    """重试支付"""
    return {
        "order_id": order_id,
        "retry_status": "success",
        "payment_url": f"https://example.com/pay/{order_id}",
    }


# ==================== 高风险工具 (始终interrupt) ====================

@tool
def issue_refund(order_id: str, amount: float, method: str, reason: str) -> dict:
    """发起退款"""
    try:
        from src.db.queries import update_order_status
        update_order_status(order_id, "refunded")
    except Exception:
        pass
    return {
        "order_id": order_id,
        "refund_amount": amount,
        "refund_method": method,
        "reason": reason,
        "refund_id": f"REF-{order_id[-3:]}",
        "status": "processing",
        "estimated_arrival": "3-5个工作日",
    }


@tool
def cancel_order(order_id: str, reason: str) -> dict:
    """取消订单"""
    try:
        from src.db.queries import get_order, update_order_status
        order = get_order(order_id)
        if not order:
            return {"error": f"订单 {order_id} 不存在"}
        update_order_status(order_id, "cancelled")
        return {
            "order_id": order_id,
            "cancel_status": "success",
            "reason": reason,
            "refund_amount": order["total_price"],
            "refund_method": "原路退回",
        }
    except Exception as e:
        return {"error": str(e)}


@tool
def process_exchange(order_id: str, original_item: str, new_item: str) -> dict:
    """处理换货"""
    return {
        "order_id": order_id,
        "original_item": original_item,
        "new_item": new_item,
        "exchange_id": f"EXC-{order_id[-3:]}",
        "status": "processing",
        "return_label": f"https://example.com/return-label/EXC-{order_id[-3:]}",
    }


@tool
def apply_compensation(customer_id: str, comp_type: str, value: float, reason: str) -> dict:
    """发放补偿"""
    return {
        "customer_id": customer_id,
        "type": comp_type,
        "value": value,
        "reason": reason,
        "compensation_id": f"CMP-{customer_id}",
        "status": "issued",
    }


@tool
def override_eligibility(order_id: str, policy_exception_reason: str) -> dict:
    """政策例外审批"""
    return {
        "order_id": order_id,
        "override_granted": True,
        "reason": policy_exception_reason,
        "approved_by": "system",
    }


# ==================== 工具分类 ====================

LOW_RISK_TOOLS = [
    check_inventory, get_order_details, track_shipment,
    check_payment_status, search_knowledge_base, search_products,
    get_product_details, recommend_size, check_return_eligibility,
    get_customer_orders, get_customer_info, check_warranty_status,
    find_promotions,
]

MEDIUM_RISK_TOOLS = [
    update_shipping_address, send_return_label,
    issue_store_credit, retry_payment,
]

HIGH_RISK_TOOLS = [
    issue_refund, cancel_order, process_exchange,
    apply_compensation, override_eligibility,
]

ALL_TOOLS = LOW_RISK_TOOLS + MEDIUM_RISK_TOOLS + HIGH_RISK_TOOLS
