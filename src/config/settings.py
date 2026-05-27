"""
项目配置

包含:
- LLM模型配置 (意图分类模型, 响应生成模型, 适配器模型)
- 风险阈值配置 (金额阈值, 质量评分阈值)
- 路由规则配置 (敏感词列表, 转人工关键词, 情感阈值)
- 子图超时配置
- 观测配置 (采样率, 埋点开关)
- 策略版本配置 (A/B测试)
"""

import os

# ==================== LLM模型配置 ====================
# 意图分类和情感检测使用较快的模型
CLASSIFIER_MODEL = os.getenv("CLASSIFIER_MODEL", "gpt-4o-mini")
# 响应生成使用高质量模型
GENERATOR_MODEL = os.getenv("GENERATOR_MODEL", "gpt-4o")
# 语气适配使用中等模型
ADAPTER_MODEL = os.getenv("ADAPTER_MODEL", "gpt-4o-mini")

# ==================== 风险阈值 ====================
# 金额阈值: 超过此金额的操作需要人工审批
AMOUNT_THRESHOLD_HIGH = 500.0       # 高风险金额阈值
AMOUNT_THRESHOLD_MEDIUM = 200.0     # 中风险金额阈值
# 质量评分阈值
QUALITY_SCORE_LOW = 0.8             # 低风险自动通过
QUALITY_SCORE_CRITICAL = 0.5        # 低于此分数需人工审核
QUALITY_SCORE_REPROCESS = 0.4       # 低于此分数重新处理
# 自动修正最大次数
MAX_AUTO_CORRECTION_ATTEMPTS = 1
# 人工审核最大轮次
MAX_HUMAN_REVIEW_ROUNDS = 2
# 澄清最大次数
MAX_CLARIFICATION_ATTEMPTS = 2
# 解析尝试最大次数
MAX_RESOLUTION_ATTEMPTS = 3

# ==================== 路由规则 ====================
# 转人工快捷匹配关键词
HUMAN_TRANSFER_PATTERNS = [
    r"人工客服", r"转人工", r"真人", r"活人",
    r"talk to human", r"human agent", r"real person",
    r"客服", r"接线员",
]
# 敏感词列表
SENSITIVE_WORDS = [
    "投诉", "315", "消费者协会", "工商局", "法院", "律师",
    "曝光", "媒体", "维权", "举报",
]
# 极端情感阈值
EMOTION_INTENSITY_THRESHOLD = 0.9
# 客户等级
CUSTOMER_TIERS = ["standard", "vip", "enterprise"]

# ==================== 子图超时配置 ====================
SUBGRAPH_TIMEOUT_SECONDS = 30       # 子图执行超时
TOOL_CALL_TIMEOUT_SECONDS = 10      # 工具调用超时
HUMAN_REVIEW_TIMEOUT_MINUTES = 15   # 人工审核超时

# ==================== 观测配置 ====================
TRACE_ENABLED = os.getenv("TRACE_ENABLED", "true").lower() == "true"
TRACE_SAMPLE_RATE = float(os.getenv("TRACE_SAMPLE_RATE", "1.0"))
EVAL_ENABLED = os.getenv("EVAL_ENABLED", "false").lower() == "true"
EVAL_SAMPLE_RATE = float(os.getenv("EVAL_SAMPLE_RATE", "0.1"))

# ==================== 策略版本 ====================
STRATEGY_VERSION = os.getenv("STRATEGY_VERSION", "v1")
PROMPT_VARIANT = os.getenv("PROMPT_VARIANT", "default")

# ==================== 历史加载 ====================
HISTORY_WINDOW_ROUNDS = 3  # 入口层加载最近3轮对话摘要

# ==================== 意图标签 ====================
INTENT_CATEGORIES = [
    "presales_consult",       # 售前咨询
    "presales_product",       # 商品咨询
    "presales_recommend",     # 推荐请求
    "insales_order",          # 订单查询
    "insales_logistics",      # 物流追踪
    "insales_payment",        # 支付问题
    "insales_modify",         # 订单修改
    "aftersales_return",      # 退货
    "aftersales_exchange",    # 换货
    "aftersales_refund",      # 退款
    "aftersales_warranty",    # 保修
    "aftersales_complaint",   # 投诉
    "complaint_product",      # 产品投诉
    "complaint_service",      # 服务投诉
    "complaint_logistics",    # 物流投诉
    "general_faq",            # 常见问题
    "general_policy",         # 政策咨询
    "general_greeting",       # 问候
]

# 意图到子图的映射
INTENT_TO_SUBGRAPH = {
    "presales_consult": "presales_agent",
    "presales_product": "presales_agent",
    "presales_recommend": "presales_agent",
    "insales_order": "insales_agent",
    "insales_logistics": "insales_agent",
    "insales_payment": "insales_agent",
    "insales_modify": "insales_agent",
    "aftersales_return": "aftersales_agent",
    "aftersales_exchange": "aftersales_agent",
    "aftersales_refund": "aftersales_agent",
    "aftersales_warranty": "aftersales_agent",
    "aftersales_complaint": "complaint_agent",
    "complaint_product": "complaint_agent",
    "complaint_service": "complaint_agent",
    "complaint_logistics": "complaint_agent",
    "general_faq": "general_agent",
    "general_policy": "general_agent",
    "general_greeting": "general_agent",
}
