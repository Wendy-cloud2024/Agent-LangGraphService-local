<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { useSessionStore } from '@/stores/session'
import { useChatStore } from '@/stores/chat'
import { wsClient } from '@/api/websocket'
import CustomerSelector from '@/components/CustomerSelector.vue'
import ChatWindow from '@/components/ChatWindow.vue'

const sessionStore = useSessionStore()
const chatStore = useChatStore()
const demoMode = ref(false)

function enableDemoMode() {
  demoMode.value = true
  sessionStore.session = {
    thread_id: 'demo-session-001',
    customer_id: 'C001',
    customer_tier: 'vip',
    customer_name: '张三',
  }
}

onMounted(async () => {
  await sessionStore.fetchCustomers().catch(() => {/* 演示模式不需要后端 */})
  wsClient.onMessage((msg) => chatStore.handleServerEvent(msg))
})

onUnmounted(() => {
  wsClient.disconnect()
})

// 切换会话时清空消息
watch(() => sessionStore.session, (val, old) => {
  if (val?.thread_id !== old?.thread_id) {
    chatStore.clearMessages()
  }
})
</script>

<template>
  <div class="min-h-screen bg-gray-50 flex flex-col">
    <!-- 无会话: 客户选择 -->
    <CustomerSelector v-if="!sessionStore.hasSession" @demo="enableDemoMode" />

    <!-- 有会话: 聊天窗口 -->
    <ChatWindow v-else :demo-mode="demoMode" />
  </div>
</template>
