/** 聊天 Store — 消息列表、处理状态、元数据 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type {
  ChatMessageItem,
  ServerEvent,
  ResponseMetadata,
  HumanReviewRequest,
  ApprovalRequest,
} from '@/types'
import { wsClient } from '@/api/websocket'

export const useChatStore = defineStore('chat', () => {
  // ---- state ----
  const messages = ref<ChatMessageItem[]>([])
  const isProcessing = ref(false)
  const nodeProgress = ref<string[]>([])
  const currentMetadata = ref<ResponseMetadata | null>(null)
  const humanReviewPending = ref<HumanReviewRequest | null>(null)
  const approvalPending = ref<ApprovalRequest | null>(null)

  // ---- getters ----
  const lastAgentMetadata = computed(() => currentMetadata.value)

  // ---- actions ----

  /** 处理从 WebSocket 收到的服务端事件 */
  function handleServerEvent(event: ServerEvent) {
    switch (event.type) {
      case 'node_progress':
        if (event.node === '__thinking__') {
          isProcessing.value = true
        } else {
          nodeProgress.value = [...nodeProgress.value, event.node]
        }
        break

      case 'chat_response':
        isProcessing.value = false
        nodeProgress.value = []
        currentMetadata.value = event.metadata
        _addMessage('agent', event.content, event.metadata)
        break

      case 'human_review_request':
        isProcessing.value = false
        humanReviewPending.value = event
        // 把待审核内容作为系统消息显示
        _addMessage('system', `[人工审核请求] 风险等级: ${event.review_info.risk_level}`)
        break

      case 'approval_request':
        isProcessing.value = false
        approvalPending.value = event
        _addMessage('system', `[投诉审批请求] 严重程度: ${event.approval_info.severity}`)
        break

      case 'status_response':
        // 状态响应由 session store 处理
        break

      case 'error':
        isProcessing.value = false
        nodeProgress.value = []
        _addMessage('system', `错误: ${event.message}`)
        break
    }
  }

  /** 发送客户消息 */
  function sendMessage(content: string) {
    if (!content.trim()) return
    _addMessage('customer', content)
    isProcessing.value = true
    nodeProgress.value = []
    wsClient.send({ type: 'chat', content })
  }

  /** 发送人工审核决策 */
  function submitHumanDecision(
    decision: 'approve' | 'edit' | 'reject_regenerate' | 'reject_reclassify' | 'takeover',
    feedback: string = '',
    editedResponse: string = '',
  ) {
    if (!humanReviewPending.value) return
    humanReviewPending.value = null
    isProcessing.value = true
    _addMessage('system', `[人工决策: ${decision}]`)
    wsClient.send({
      type: 'human_decision',
      decision,
      feedback,
      edited_response: editedResponse,
    })
  }

  /** 发送审批决策 */
  function submitApproval(approved: boolean, note: string = '') {
    if (!approvalPending.value) return
    approvalPending.value = null
    isProcessing.value = true
    _addMessage('system', `[审批决策: ${approved ? '批准' : '拒绝'}]`)
    wsClient.send({ type: 'approval', approved, note })
  }

  /** 清空消息 */
  function clearMessages() {
    messages.value = []
    nodeProgress.value = []
    currentMetadata.value = null
    humanReviewPending.value = null
    approvalPending.value = null
    isProcessing.value = false
  }

  // ---- helpers ----

  let _msgId = 0
  function _addMessage(role: ChatMessageItem['role'], content: string, metadata?: ResponseMetadata) {
    messages.value.push({
      id: `msg-${++_msgId}`,
      role,
      content,
      metadata,
      timestamp: Date.now(),
    })
  }

  return {
    messages,
    isProcessing,
    nodeProgress,
    currentMetadata,
    humanReviewPending,
    approvalPending,
    lastAgentMetadata,
    handleServerEvent,
    sendMessage,
    submitHumanDecision,
    submitApproval,
    clearMessages,
  }
})
