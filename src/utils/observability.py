"""
全链路观测工具

每个主要节点调用 trace() 写入观测事件:
  trace(trace_id, node, status, duration_ms, metadata)

关键度量指标:
- 平均处理时长
- 分诊准确率
- 人工升级率
- 自动修正成功率
- 子图调用成功率
- 澄清回路触发率
- Fallback降级率
- 客户满意度(CSAT)
"""
