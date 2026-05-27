"""
语气与合规适配器

职责:
- 根据 emotion/customer_tier 调整语气
- 应用 strategy_version 对应的 prompt 变体 (A/B测试)
- 根据品牌调性调整措辞
- 标注引用来源
- 支持 output_gate 中风险自动修正时的改写指导
- 输出 draft_response
"""
