"""
人工审核断点节点

LangGraph interrupt() 实现, 暂停执行等待人工决策。

人工决策5种:
  批准 → output_gate复查 → respond_to_customer
  编辑 → output_gate复查 → respond_to_customer
  拒绝-重生成 → content_merger (沿用子图结果重新生成)
  拒绝-重分诊 → orchestrator_gate (轻量模式, 仅重做意图分类)
  接管 → escalate_to_human + 设置session.takeover=True

安全闭环: 人工输出必须过output_gate复查, 最多2轮防死循环。
"""
