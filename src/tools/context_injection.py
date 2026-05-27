"""
Supervisor上下文注入 (v4)

由supervisor在调用子图前根据意图类型注入相关上下文。
子图通过 state["relevant_history"] 获取, 不直接访问外部存储。

inject_subgraph_context(state, subgraph_name) -> dict:
  根据子图类型拉取相关数据:
    aftersales → 售后相关对话 + 相关订单
    complaint  → 客户订单历史 + 类似投诉案例
    insales    → 相关订单的对话历史
    presales   → 客户之前浏览/咨询过的商品
    general    → 最近对话摘要
"""
