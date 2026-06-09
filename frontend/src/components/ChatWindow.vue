<script setup lang="ts">
import { ref, nextTick, watch } from 'vue'
import { useSessionStore } from '@/stores/session'
import { useChatStore } from '@/stores/chat'
import StatusBar from '@/components/StatusBar.vue'
import MessageBubble from '@/components/MessageBubble.vue'
import MessageInput from '@/components/MessageInput.vue'
import HumanReviewPanel from '@/components/HumanReviewPanel.vue'
import AgentMetadata from '@/components/AgentMetadata.vue'

const sessionStore = useSessionStore()
const chatStore = useChatStore()

const messagesContainer = ref<HTMLElement | null>(null)

// 新消息时自动滚动到底部
watch(() => chatStore.messages.length, async () => {
  await nextTick()
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  }
})
</script>

<template>
  <div class="flex flex-col h-screen max-w-3xl mx-auto">
    <!-- 顶部状态栏 -->
    <StatusBar />

    <!-- 消息列表 -->
    <div ref="messagesContainer" class="flex-1 overflow-y-auto px-4 py-4 space-y-3">
      <MessageBubble
        v-for="msg in chatStore.messages"
        :key="msg.id"
        :message="msg"
      />

      <!-- 处理中提示 -->
      <div v-if="chatStore.isProcessing" class="flex items-center gap-2 px-4 py-2">
        <div class="flex gap-1">
          <span class="w-2 h-2 rounded-full bg-blue-400 animate-bounce" style="animation-delay: 0ms"></span>
          <span class="w-2 h-2 rounded-full bg-blue-400 animate-bounce" style="animation-delay: 150ms"></span>
          <span class="w-2 h-2 rounded-full bg-blue-400 animate-bounce" style="animation-delay: 300ms"></span>
        </div>
        <span class="text-sm text-gray-400">AI 正在思考...</span>
      </div>
    </div>

    <!-- 元数据面板 -->
    <AgentMetadata v-if="chatStore.lastAgentMetadata" />

    <!-- 人工审核面板 -->
    <HumanReviewPanel v-if="chatStore.humanReviewPending" />

    <!-- 节点进度 -->
    <div v-if="chatStore.nodeProgress.length > 0" class="px-4 py-2 border-t border-gray-100">
      <div class="flex items-center gap-1 flex-wrap text-xs text-gray-400">
        <span>执行路径:</span>
        <template v-for="(node, i) in chatStore.nodeProgress" :key="i">
          <span class="text-blue-500">{{ node }}</span>
          <span v-if="i < chatStore.nodeProgress.length - 1">→</span>
        </template>
      </div>
    </div>

    <!-- 输入框 -->
    <MessageInput />
  </div>
</template>
