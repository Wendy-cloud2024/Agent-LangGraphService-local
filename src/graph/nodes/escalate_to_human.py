"""
转接人工节点

职责:
- 编制交接摘要 (问题, AI操作, 客户情感, 相关订单)
- 分配给可用人工客服
- 向客户发送转接通知
- 写入观测埋点
- 设置 resolution_status = "escalated"
- 如果是"接管"模式: 设置 session.takeover=True
"""
