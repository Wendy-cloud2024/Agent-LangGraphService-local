<script setup lang="ts">
import { onMounted, onUnmounted, watch } from 'vue'
import { useSessionStore } from '@/stores/session'
import { useChatStore } from '@/stores/chat'
import { wsClient } from '@/api/websocket'
import CustomerSelector from '@/components/CustomerSelector.vue'
import ChatWindow from '@/components/ChatWindow.vue'

const sessionStore = useSessionStore()
const chatStore = useChatStore()

onMounted(async () => {
  await sessionStore.fetchCustomers()
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
    <CustomerSelector v-if="!sessionStore.hasSession" />

    <!-- 有会话: 聊天窗口 -->
    <ChatWindow v-else />
  </div>
</template>
