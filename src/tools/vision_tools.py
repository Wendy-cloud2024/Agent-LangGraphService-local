"""
专项视觉工具集 (@tool装饰函数)

各子图内部调用的专项图像分析工具:

售前: visual_product_match(image)     → 客户拍照匹配SKU
售中: ocr_shipping_label(image)       → 解析物流面单运单号/条码
售后: detect_product_damage(image)    → 判断破损程度/保修范围
售后: ocr_product_label(image)        → 读取商品标签/成分表/批号
投诉: detect_quality_issue(image)     → 识别质量问题(色差/做工缺陷)

注意: orchestrator_gate仅做通用图片描述和安全检查,
      专项识别下沉到各子图内部通过这些工具完成。
"""

import logging
from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def visual_product_match(image_data: str) -> dict:
    """售前: 客户拍照匹配SKU商品

    参数:
        image_data: 图片数据(base64编码或URL)
    """
    # Mock实现 - 实际项目中调用视觉匹配API
    return {
        "matched": True,
        "sku": "SKU-PRODUCT-001",
        "product_name": "示例商品",
        "category": "电子产品",
        "price": 299.0,
        "similarity": 0.92,
        "alternatives": [
            {"sku": "SKU-PRODUCT-002", "name": "相似商品A", "similarity": 0.85},
        ],
    }


@tool
def ocr_shipping_label(image_data: str) -> dict:
    """售中: 解析物流面单的运单号、条码

    参数:
        image_data: 物流面单图片数据
    """
    return {
        "tracking_number": "SF1234567890",
        "carrier": "顺丰速运",
        "sender": {"name": "xxx旗舰店", "phone": "400-xxx-xxxx"},
        "recipient": {"name": "张**", "address": "上海市xxx"},
        "barcode": "1234567890123",
        "confidence": 0.95,
    }


@tool
def detect_product_damage(image_data: str) -> dict:
    """售后: 判断破损程度、是否在保修范围

    参数:
        image_data: 破损商品图片数据
    """
    return {
        "damage_detected": True,
        "damage_type": "crack",
        "severity": "moderate",
        "location": "底部",
        "description": "底部有明显裂纹，非正常使用磨损",
        "warranty_covered": True,
        "cause": "运输损坏",
        "confidence": 0.88,
    }


@tool
def ocr_product_label(image_data: str) -> dict:
    """售后: 读取商品标签、成分表、批号

    参数:
        image_data: 商品标签图片数据
    """
    return {
        "product_name": "示例商品",
        "batch_number": "BN20240115",
        "manufacture_date": "2024-01-15",
        "expiry_date": "2025-01-15",
        "ingredients": ["成分1", "成分2", "成分3"],
        "manufacturer": "xxx制造有限公司",
        "confidence": 0.90,
    }


@tool
def detect_quality_issue(image_data: str) -> dict:
    """投诉: 识别质量问题(色差、做工缺陷等)

    参数:
        image_data: 问题商品图片数据
    """
    return {
        "issue_detected": True,
        "issue_type": "color_mismatch",
        "description": "实物与图片存在明显色差",
        "severity": "moderate",
        "evidence_strength": "strong",
        "suggested_action": "换货或退款",
        "confidence": 0.85,
    }


# 按子图分类的视觉工具
PRESALES_VISION_TOOLS = [visual_product_match]
INSALES_VISION_TOOLS = [ocr_shipping_label]
AFTERSALES_VISION_TOOLS = [detect_product_damage, ocr_product_label]
COMPLAINT_VISION_TOOLS = [detect_quality_issue]
