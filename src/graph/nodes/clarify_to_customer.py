"""
澄清追问旁路节点

独立于主线路径, 绕过 content_merger/tone_adapter/output_gate。

流程:
- 从 clarification_request 生成追问消息
- 仅做基本安全检查 (PII过滤, 有害内容检测)
- 直接发送给客户
- 设置 pending_clarification=True + pending_subgraph + pending_accumulated_state
- 客户回复后由 orchestrator_gate 第⓪步捕获并路由回原子图
"""
