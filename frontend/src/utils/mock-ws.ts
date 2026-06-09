/**
 * 演示模式 — 模拟 WebSocket 服务端事件，展示人工审核 UI 流程
 *
 * 使用方式：在前端 store 中调用 simulateDemo() 即可看到完整流程
 */

import type { ServerEvent } from '@/types'

/** 延迟辅助 */
const delay = (ms: number) => new Promise(r => setTimeout(r, ms))

/** 模拟一次正常对话（低风险） */
export async function simulateNormalChat(handleEvent: (e: ServerEvent) => void) {
  // 节点进度
  const nodes = [
    { node: 'orchestrator_gate', tags: { emotion: 'neutral', urgency: 'low' } },
    { node: 'presales_agent', tags: {} },
    { node: 'content_merger', tags: {} },
    { node: 'tone_adapter', tags: {} },
    { node: 'output_gate', tags: { risk_level: 'low', quality_score: 0.92 } },
    { node: 'respond_to_customer', tags: { resolution_status: 'resolved' } },
  ]

  for (const n of nodes) {
    await delay(500)
    handleEvent({ type: 'node_progress', ...n })
  }

  await delay(300)
  handleEvent({
    type: 'chat_response',
    content: '您好！我们这款经典纯棉T恤目前有黑色和白色两种颜色，库存充足。尺码从S到XXL都有，价格是¥99。需要我为您推荐合适的尺码吗？',
    metadata: {
      intent_labels: [{ intent: 'presales_product_inquiry', confidence: 0.92, primary: true }],
      emotion: 'neutral',
      emotion_intensity: 0.1,
      urgency: 'low',
      routing_reason: '意图路由: presales_product_inquiry',
      active_agents: ['presales_agent'],
      risk_level: 'low',
      quality_score: 0.92,
      resolution_status: 'resolved',
      session_takeover: false,
    },
  })
}

/** 模拟触发人工审核（高风险） */
export async function simulateHumanReview(handleEvent: (e: ServerEvent) => void) {
  const nodes = [
    { node: 'orchestrator_gate', tags: { emotion: 'angry', urgency: 'high' } },
    { node: 'aftersales_agent', tags: {} },
    { node: 'content_merger', tags: {} },
    { node: 'tone_adapter', tags: {} },
    { node: 'output_gate', tags: { risk_level: 'high', quality_score: 0.42 } },
    { node: 'human_review', tags: { requires_human_review: true } },
  ]

  for (const n of nodes) {
    await delay(600)
    handleEvent({ type: 'node_progress', ...n })
  }

  await delay(500)
  handleEvent({
    type: 'human_review_request',
    review_info: {
      draft_response: '非常抱歉给您带来不好的体验！我们已经查实您的订单确实存在物流延迟问题。考虑到您是VIP客户，我们愿意为您提供全额退款并额外补偿¥50优惠券，您看这样可以吗？',
      risk_level: 'high',
      quality_score: 0.42,
      safety_flags: [],
      human_review_reason: '高风险操作：涉及全额退款（¥299）+ 补偿（¥50）',
      review_round: 1,
    },
  })
}

/** 模拟人工审核通过后的流程 */
export async function simulateApproveAfterReview(handleEvent: (e: ServerEvent) => void) {
  const nodes = [
    { node: 'output_gate', tags: { risk_level: 'low', quality_score: 0.88 } },
    { node: 'respond_to_customer', tags: { resolution_status: 'resolved' } },
  ]

  for (const n of nodes) {
    await delay(600)
    handleEvent({ type: 'node_progress', ...n })
  }

  await delay(300)
  handleEvent({
    type: 'chat_response',
    content: '非常抱歉给您带来不好的体验！我们已经为您办理了全额退款¥299，同时为您发放了¥50优惠券（有效期30天）。退款将在1-3个工作日内到账。如果您还有其他问题，欢迎随时咨询！',
    metadata: {
      intent_labels: [{ intent: 'aftersales_refund', confidence: 0.95, primary: true }],
      emotion: 'empathetic',
      emotion_intensity: 0.3,
      urgency: 'high',
      routing_reason: '人工审核通过: 批准退款+补偿方案',
      active_agents: ['aftersales_agent'],
      risk_level: 'low',
      quality_score: 0.88,
      resolution_status: 'resolved',
      session_takeover: false,
    },
  })
}

/** 模拟投诉审批流程 */
export async function simulateComplaintApproval(handleEvent: (e: ServerEvent) => void) {
  const nodes = [
    { node: 'orchestrator_gate', tags: { emotion: 'angry', urgency: 'critical' } },
    { node: 'complaint_agent', tags: {} },
    { node: 'approval_gate', tags: {} },
  ]

  for (const n of nodes) {
    await delay(600)
    handleEvent({ type: 'node_progress', ...n })
  }

  await delay(500)
  handleEvent({
    type: 'approval_request',
    approval_info: {
      complaint_type: 'product_quality',
      severity: 'high',
      compensation_value: 100,
      plan: {
        resolution: '退货退款 + 双倍补偿',
        compensation_type: 'store_credit',
      },
    },
  })
}

/** 模拟澄清回路 */
export async function simulateClarification(handleEvent: (e: ServerEvent) => void) {
  const nodes = [
    { node: 'orchestrator_gate', tags: { emotion: 'neutral', urgency: 'medium' } },
    { node: 'aftersales_agent', tags: {} },
    { node: 'subgraph_output_router', tags: {} },
    { node: 'clarify_to_customer', tags: {} },
  ]

  for (const n of nodes) {
    await delay(500)
    handleEvent({ type: 'node_progress', ...n })
  }

  await delay(300)
  handleEvent({
    type: 'chat_response',
    content: '好的，我来帮您处理退货。请问您要退货的订单号是多少呢？',
    metadata: {
      intent_labels: [{ intent: 'aftersales_return', confidence: 0.88, primary: true }],
      emotion: 'neutral',
      emotion_intensity: 0.1,
      urgency: 'medium',
      routing_reason: '澄清回路: 缺少订单号',
      active_agents: ['aftersales_agent'],
      risk_level: 'low',
      quality_score: 0.95,
      resolution_status: 'clarifying',
      session_takeover: false,
    },
  })
}
