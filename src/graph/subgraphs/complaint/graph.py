"""
投诉Agent子图 (最高优先级)

节点:
  1. complaint_classifier → 分类投诉类型和严重度
  2. context_gatherer     → 并行收集上下文 (订单历史/类似案例/政策例外)
  3. empathy_responder    → 共情回应
  4. resolution_planner   → 提出补偿方案
  5. approval_gate        → 人工审批 [interrupt()断点]
  6. complaint_respond    → 编译回复

快速通道: critical + angry → 跳过resolution_planner直接到approval_gate
不降级: 异常时直接escalate_to_human, 不走fallback

专项视觉工具: detect_quality_issue(image)
输出类型: normal | escalate
"""
