"""
数据库查询函数

为 agent 工具提供所有数据查询接口。
"""

import logging
from src.db.connection import get_db, dict_from_row, dicts_from_rows

logger = logging.getLogger(__name__)


# ==================== 商品查询 ====================

def get_product(sku: str) -> dict | None:
    """查询商品基本信息"""
    db = get_db()
    row = db.execute("SELECT * FROM products WHERE sku = ?", (sku,)).fetchone()
    db.close()
    return dict_from_row(row)


def search_products(keyword: str) -> list[dict]:
    """按关键词搜索商品（名称/类别/颜色/材质）"""
    db = get_db()
    pattern = f"%{keyword}%"
    rows = db.execute(
        "SELECT * FROM products WHERE status='active' AND "
        "(name LIKE ? OR category LIKE ? OR color LIKE ? OR material LIKE ?)",
        (pattern, pattern, pattern, pattern)
    ).fetchall()
    db.close()
    return dicts_from_rows(rows)


def get_product_all_details(sku: str) -> list[dict]:
    """查询商品所有尺码数据"""
    db = get_db()
    rows = db.execute(
        "SELECT * FROM product_details WHERE sku = ? ORDER BY "
        "CASE size WHEN 'S' THEN 1 WHEN 'M' THEN 2 WHEN 'L' THEN 3 "
        "WHEN 'XL' THEN 4 WHEN 'XXL' THEN 5 END",
        (sku,)
    ).fetchall()
    db.close()
    return dicts_from_rows(rows)


def get_size_recommendation(sku: str, height: float, weight: float) -> dict | None:
    """根据身高体重推荐尺码

    解析 height_range 和 weight_range，找到匹配的尺码。
    如果刚好在边界，推荐大一码。
    """
    details = get_product_all_details(sku)
    if not details:
        return None

    best_match = None
    for d in details:
        h_range = d.get("height_range", "")
        w_range = d.get("weight_range", "")

        h_min, h_max = _parse_range(h_range, "cm")
        w_min, w_max = _parse_range(w_range, "kg")

        if h_min <= height <= h_max and w_min <= weight <= w_max:
            best_match = d
            # 不 break，继续找更精确的

    if best_match:
        return {
            "recommended_size": best_match["size"],
            "reason": f"身高{height}cm({best_match['height_range']})，体重{weight}kg({best_match['weight_range']})",
            "details": best_match,
            "product_sku": sku,
        }

    # 没有精确匹配，找最接近的
    return _find_closest_size(details, height, weight, sku)


def _parse_range(range_str: str, unit: str) -> tuple[float, float]:
    """解析 "165-170cm" → (165, 170)"""
    try:
        cleaned = range_str.replace(unit, "").replace(" ", "")
        parts = cleaned.split("-")
        return float(parts[0]), float(parts[1])
    except (ValueError, IndexError):
        return 0.0, 999.0


def _find_closest_size(details: list[dict], height: float, weight: float, sku: str) -> dict:
    """找最接近的尺码（超出范围时）"""
    best = None
    best_dist = float("inf")
    for d in details:
        h_min, h_max = _parse_range(d.get("height_range", ""), "cm")
        w_min, w_max = _parse_range(d.get("weight_range", ""), "kg")
        h_mid = (h_min + h_max) / 2
        w_mid = (w_min + w_max) / 2
        dist = abs(height - h_mid) + abs(weight - w_mid) * 2
        if dist < best_dist:
            best_dist = dist
            best = d

    if best:
        return {
            "recommended_size": best["size"],
            "reason": f"身高{height}cm、体重{weight}kg接近{best['height_range']}、{best['weight_range']}范围",
            "details": best,
            "product_sku": sku,
            "note": "非精确匹配，建议参考尺码表确认",
        }
    return None


# ==================== 客户查询 ====================

def get_customer(customer_id: str) -> dict | None:
    """查询客户信息（含身高体重）"""
    db = get_db()
    row = db.execute("SELECT * FROM customers WHERE customer_id = ?", (customer_id,)).fetchone()
    db.close()
    return dict_from_row(row)


# ==================== 订单查询 ====================

def get_order(order_id: str) -> dict | None:
    """查询订单详情"""
    db = get_db()
    row = db.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,)).fetchone()
    db.close()
    return dict_from_row(row)


def get_customer_orders(customer_id: str, limit: int = 10) -> list[dict]:
    """查询客户历史订单"""
    db = get_db()
    rows = db.execute(
        "SELECT * FROM orders WHERE customer_id = ? ORDER BY created_at DESC LIMIT ?",
        (customer_id, limit)
    ).fetchall()
    db.close()
    return dicts_from_rows(rows)


# ==================== 物流查询 ====================

def get_tracking(tracking_number: str) -> dict:
    """查询物流信息（模拟）"""
    # 物流数据不在数据库中，返回模拟信息
    # 实际项目中调用物流API
    return {
        "tracking_number": tracking_number,
        "carrier": "顺丰速运" if tracking_number.startswith("SF") else "圆通速递",
        "status": "in_transit",
        "estimated_delivery": "2024-01-22",
        "updates": [
            {"time": "2024-01-20 14:00", "location": "上海转运中心", "status": "已到达"},
            {"time": "2024-01-20 08:00", "location": "杭州集散中心", "status": "已发出"},
        ],
    }


# ==================== 写入操作 ====================

def update_order_status(order_id: str, status: str) -> bool:
    """更新订单状态"""
    db = get_db()
    db.execute(
        "UPDATE orders SET status = ?, updated_at = datetime('now') WHERE order_id = ?",
        (status, order_id)
    )
    db.commit()
    affected = db.execute("SELECT changes()").fetchone()[0]
    db.close()
    return affected > 0
