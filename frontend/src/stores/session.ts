/** 会话 Store — 客户信息、会话管理 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { Customer, SessionInfo } from '@/types'
import { wsClient } from '@/api/websocket'

export const useSessionStore = defineStore('session', () => {
  // ---- state ----
  const customers = ref<Customer[]>([])
  const session = ref<SessionInfo | null>(null)
  const connected = ref(false)
  const sessionTakeover = ref(false)

  // ---- getters ----
  const hasSession = computed(() => !!session.value)
  const customerName = computed(() => session.value?.customer_name ?? '')

  // ---- actions ----

  /** 从 REST API 加载客户列表 */
  async function fetchCustomers() {
    const resp = await fetch('/api/customers')
    customers.value = await resp.json()
  }

  /** 创建新会话并连接 WebSocket */
  async function createSession(customerId: string, tier: string = 'standard') {
    const resp = await fetch('/api/sessions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ customer_id: customerId, customer_tier: tier }),
    })
    const data = await resp.json()
    session.value = {
      thread_id: data.thread_id,
      customer_id: data.customer_id,
      customer_tier: data.customer_tier,
      customer_name: data.customer_name,
    }
    // 连接 WebSocket
    wsClient.connect(data.thread_id)
  }

  /** 结束会话 */
  async function endSession() {
    if (!session.value) return
    await fetch(`/api/sessions/${session.value.thread_id}/end`, { method: 'POST' })
    wsClient.disconnect()
    session.value = null
    sessionTakeover.value = false
  }

  /** 释放接管 */
  function sendEndTakeover() {
    wsClient.send({ type: 'end_takeover' })
  }

  return {
    customers,
    session,
    connected,
    sessionTakeover,
    hasSession,
    customerName,
    fetchCustomers,
    createSession,
    endSession,
    sendEndTakeover,
  }
})
