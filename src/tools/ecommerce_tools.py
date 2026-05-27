"""
电商后端工具集 (@tool装饰函数)

低风险 (全自动):
  check_inventory(sku, region)
  get_order_details(order_id)
  track_shipment(tracking_number)
  check_payment_status(order_id)
  search_knowledge_base(query)
  check_return_eligibility(order_id, item_id)
  find_promotions(product_ids, customer_tier)
  get_customer_orders(customer_id, limit)
  check_warranty_status(product_id, purchase_date)

中风险 (条件性interrupt):
  update_shipping_address(order_id, new_address)  → >200或跨国需审批
  update_order_quantity(order_id, item_id, qty)   → >500需审批
  send_return_label(order_id, item_id)            → 全自动
  issue_store_credit(customer_id, amount, reason) → >50需审批
  retry_payment(order_id)                         → 全自动

高风险 (始终interrupt):
  issue_refund(order_id, amount, method, reason)
  cancel_order(order_id, reason)
  process_exchange(order_id, original_item, new_item)
  apply_compensation(customer_id, type, value, reason)
  override_eligibility(order_id, policy_exception_reason)
"""

import logging
from langchain_core.tools import tool

from src.config.settings import (
    AMOUNT_THRESHOLD_HIGH,
    AMOUNT_THRESHOLD_MEDIUM,
)

logger = logging.getLogger(__name__)


# ==================== 低风险工具 (全自动) ====================

@tool
def check_inventory(sku: str, region: str = "default") -> dict:
    """查询商品库存"""
    # Mock实现
    return {
        "sku": sku,
        "region": region,
        "available": True,
        "quantity": 150,
        "warehouse": "华东仓",
    }


@tool
def get_order_details(order_id: str) -> dict:
    """获取订单详情"""
    return {
        "order_id": order_id,
        "status": "shipped",
        "items": [{"sku": "SKU001", "name": "商品A", "quantity": 1, "price": 299.0}],
        "total": 299.0,
        "created_at": "2024-01-15T10:30:00",
        "shipping_address": "上海市浦东新区xxx",
        "tracking_number": "SF1234567890",
    }


@tool
def track_shipment(tracking_number: str) -> dict:
    """物流追踪"""
    return {
        "tracking_number": tracking_number,
        "carrier": "顺丰速运",
        "status": "in_transit",
        "estimated_delivery": "2024-01-18",
        "updates": [
            {"time": "2024-01-16 14:00", "location": "上海转运中心", "status": "已到达"},
            {"time": "2024-01-16 08:00", "location": "杭州集散中心", "status": "已发出"},
        ],
    }


@tool
def check_payment_status(order_id: str) -> dict:
    """查询支付状态"""
    return {
        "order_id": order_id,
        "payment_status": "paid",
        "payment_method": "wechat",
        "amount": 299.0,
        "paid_at": "2024-01-15T10:31:00",
    }


@tool
def search_knowledge_base(query: str) -> dict:
    """搜索知识库"""
    return {
        "query": query,
        "results": [
            {"title": "退换货政策", "content": "7天无理由退换...", "relevance": 0.95},
        ],
    }


@tool
def check_return_eligibility(order_id: str, item_id: str = "") -> dict:
    """检查退货资格"""
    return {
        "order_id": order_id,
        "eligible": True,
        "reason": "在7天退货期内",
        "deadline": "2024-01-22",
        "conditions": ["商品需保持原包装", "配件齐全"],
    }


@tool
def find_promotions(product_ids: list[str], customer_tier: str = "standard") -> dict:
    """查找可用优惠"""
    promos = []
    if customer_tier == "vip":
        promos.append({"name": "VIP专享9折", "discount": 0.1, "code": "VIP10"})
    promos.append({"name": "满200减20", "discount": 20, "code": "SAVE20"})
    return {"promotions": promos}


@tool
def get_customer_orders(customer_id: str, limit: int = 5) -> dict:
    """获取客户订单列表"""
    return {
        "customer_id": customer_id,
        "orders": [
            {"order_id": "ORD001", "status": "delivered", "total": 299.0},
            {"order_id": "ORD002", "status": "shipped", "total": 159.0},
        ],
        "total_count": 2,
    }


@tool
def check_warranty_status(product_id: str, purchase_date: str) -> dict:
    """检查保修状态"""
    return {
        "product_id": product_id,
        "warranty_status": "active",
        "expiry_date": "2025-01-15",
        "warranty_type": "标准保修1年",
    }


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
def update_order_quantity(order_id: str, item_id: str, quantity: int) -> dict:
    """修改订单数量"""
    return {
        "order_id": order_id,
        "item_id": item_id,
        "new_quantity": quantity,
        "updated": True,
    }


@tool
def send_return_label(order_id: str, item_id: str = "") -> dict:
    """发送退货标签"""
    return {
        "order_id": order_id,
        "label_url": "https://example.com/return-label/ORD001",
        "tracking_number": "RT1234567890",
        "instructions": "请打印退货标签并贴在包裹上，前往最近的快递点寄回。",
    }


@tool
def issue_store_credit(customer_id: str, amount: float, reason: str) -> dict:
    """发放店铺积分（金额>50需审批）"""
    return {
        "customer_id": customer_id,
        "amount": amount,
        "reason": reason,
        "credit_id": "CRT001",
        "issued": True,
    }


@tool
def retry_payment(order_id: str) -> dict:
    """重试支付"""
    return {
        "order_id": order_id,
        "retry_status": "success",
        "payment_url": "https://example.com/pay/ORD001",
    }


# ==================== 高风险工具 (始终interrupt) ====================

@tool
def issue_refund(order_id: str, amount: float, method: str, reason: str) -> dict:
    """发起退款"""
    return {
        "order_id": order_id,
        "refund_amount": amount,
        "refund_method": method,
        "reason": reason,
        "refund_id": "REF001",
        "status": "processing",
        "estimated_arrival": "3-5个工作日",
    }


@tool
def cancel_order(order_id: str, reason: str) -> dict:
    """取消订单"""
    return {
        "order_id": order_id,
        "cancel_status": "success",
        "reason": reason,
        "refund_amount": 299.0,
        "refund_method": "原路退回",
    }


@tool
def process_exchange(order_id: str, original_item: str, new_item: str) -> dict:
    """处理换货"""
    return {
        "order_id": order_id,
        "original_item": original_item,
        "new_item": new_item,
        "exchange_id": "EXC001",
        "status": "processing",
        "return_label": "https://example.com/return-label/EXC001",
    }


@tool
def apply_compensation(customer_id: str, comp_type: str, value: float, reason: str) -> dict:
    """发放补偿"""
    return {
        "customer_id": customer_id,
        "type": comp_type,
        "value": value,
        "reason": reason,
        "compensation_id": "CMP001",
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
    check_payment_status, search_knowledge_base,
    check_return_eligibility, find_promotions,
    get_customer_orders, check_warranty_status,
]

MEDIUM_RISK_TOOLS = [
    update_shipping_address, update_order_quantity,
    send_return_label, issue_store_credit, retry_payment,
]

HIGH_RISK_TOOLS = [
    issue_refund, cancel_order, process_exchange,
    apply_compensation, override_eligibility,
]

ALL_TOOLS = LOW_RISK_TOOLS + MEDIUM_RISK_TOOLS + HIGH_RISK_TOOLS
