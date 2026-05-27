"""
子图输出统一路由器

接收所有并行子图的输出, 按优先级依次检查:
  优先级1: escalate信号 → 中断其他子图 → complaint_agent或escalate_to_human
  优先级2: clarification_request → clarify_to_customer (忽略其他结果)
  优先级3: fallback标记 → 预置话术替换, 与正常结果一起进merger
  优先级4: 全部正常 → content_merger
"""
