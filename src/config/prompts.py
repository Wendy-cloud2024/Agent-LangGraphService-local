"""
Prompt模板库

按策略版本管理所有prompt模板:
- 意图分类prompt (orchestrator_gate)
- 情感检测prompt (orchestrator_gate)
- 语气适配prompt (tone_adapter, 按emotion/tier变体)
- 响应模板 (content_merger, 按优先级模板)
- 澄清追问模板 (clarify_to_customer)
- 降级话术 (fallback预置话术)
- 交接摘要模板 (escalate_to_human)

支持 strategy_version 切换不同prompt变体。
"""
