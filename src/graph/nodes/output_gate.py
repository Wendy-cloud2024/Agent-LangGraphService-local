"""
输出关卡节点

三级路由:
  低风险 (risk=low, quality>=0.8) → respond_to_customer (全自动)
  中风险 (risk=medium, auto_correction_attempts<1) → tone_adapter (自动修正循环, 最多1次)
  中风险 (修正后仍不通过, attempts>=1) → human_review (直接升级为高风险)
  高风险 (risk=high, quality<0.5) → human_review (人工审核断点)
  关键 (risk=critical) → escalate_to_human

检查项: 安全(PII/有害内容), 质量评分, 风险评估
"""
