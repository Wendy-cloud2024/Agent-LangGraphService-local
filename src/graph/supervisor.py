"""
顶层监督者 StateGraph

组装完整的监督者图:
  orchestrator_gate → [子图并行扇出] → subgraph_output_router
  → content_merger → tone_adapter → output_gate
  → respond_to_customer | human_review | escalate_to_human

包含:
- 图节点注册
- 条件边定义 (route_by_labels, three_way_route, route_after_subgraph)
- 检查点配置 (MemorySaver/DatabaseCheckpointer)
- 子图编译与挂载
"""
