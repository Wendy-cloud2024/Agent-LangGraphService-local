/** WebSocket 消息协议 — TypeScript 接口 */

// ==================== 服务端 → 客户端 ====================

export interface ResponseMetadata {
  intent_labels: Array<{ intent: string; confidence: number; primary: boolean }>
  emotion: string
  emotion_intensity: number
  urgency: string
  routing_reason: string
  active_agents: string[]
  risk_level: string
  quality_score: number
  resolution_status: string
  session_takeover: boolean
}

export interface NodeProgress {
  type: 'node_progress'
  node: string
  tags: Record<string, unknown>
}

export interface ChatResponse {
  type: 'chat_response'
  content: string
  metadata: ResponseMetadata
}

export interface HumanReviewRequest {
  type: 'human_review_request'
  review_info: {
    draft_response: string
    risk_level: string
    quality_score: number
    safety_flags: string[]
    human_review_reason: string
    review_round: number
  }
}

export interface ApprovalRequest {
  type: 'approval_request'
  approval_info: {
    complaint_type: string
    severity: string
    compensation_value: number
    plan: Record<string, unknown>
  }
}

export interface StatusResponse {
  type: 'status_response'
  takeover: boolean
  resolution_status: string
  message_count: number
  pending_nodes: string[]
}

export interface ErrorEvent {
  type: 'error'
  message: string
}

export type ServerEvent =
  | NodeProgress
  | ChatResponse
  | HumanReviewRequest
  | ApprovalRequest
  | StatusResponse
  | ErrorEvent

// ==================== 客户端 → 服务端 ====================

export interface ChatMessage {
  type: 'chat'
  content: string
}

export interface HumanDecision {
  type: 'human_decision'
  decision: 'approve' | 'edit' | 'reject_regenerate' | 'reject_reclassify' | 'takeover'
  feedback: string
  edited_response: string
}

export interface ApprovalDecision {
  type: 'approval'
  approved: boolean
  note: string
}

export interface EndTakeover {
  type: 'end_takeover'
}

export interface GetStatus {
  type: 'get_status'
}

// ==================== 业务模型 ====================

export interface Customer {
  customer_id: string
  name: string
  gender: string
  height: number
  weight: number
  phone: string
  address: string
}

export interface SessionInfo {
  thread_id: string
  customer_id: string
  customer_tier: string
  customer_name: string
}

export interface ChatMessageItem {
  id: string
  role: 'customer' | 'agent' | 'system'
  content: string
  metadata?: ResponseMetadata
  timestamp: number
}
