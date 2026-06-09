<script setup lang="ts">
import { ref } from 'vue'
import { useSessionStore } from '@/stores/session'
import { useChatStore } from '@/stores/chat'

const sessionStore = useSessionStore()
const chatStore = useChatStore()

const inputText = ref('')

function handleSend() {
  const text = inputText.value.trim()
  if (!text || chatStore.isProcessing) return
  chatStore.sendMessage(text)
  inputText.value = ''
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    handleSend()
  }
}
</script>

<template>
  <div class="border-t border-gray-200 bg-white px-4 py-3">
    <!-- 接管模式提示 -->
    <div v-if="sessionStore.sessionTakeover" class="mb-2 flex items-center justify-between">
      <span class="text-xs text-orange-600 bg-orange-50 px-2 py-1 rounded">
        👤 接管模式 — 人工客服回复中
      </span>
      <button
        @click="sessionStore.sendEndTakeover()"
        class="text-xs text-gray-400 hover:text-red-500 transition-colors cursor-pointer"
      >
        结束接管
      </button>
    </div>

    <div class="flex items-end gap-2">
      <textarea
        v-model="inputText"
        @keydown="handleKeydown"
        :placeholder="sessionStore.sessionTakeover ? '人工客服输入回复...' : '输入消息...'"
        :disabled="chatStore.isProcessing"
        rows="1"
        class="flex-1 resize-none rounded-xl border border-gray-300 px-4 py-2.5
               focus:outline-none focus:border-blue-400 focus:ring-1 focus:ring-blue-400
               disabled:bg-gray-100 disabled:text-gray-400
               text-sm text-gray-800 transition-colors"
        @input="(e: Event) => {
          const t = e.target as HTMLTextAreaElement
          t.style.height = 'auto'
          t.style.height = Math.min(t.scrollHeight, 120) + 'px'
        }"
      />
      <button
        @click="handleSend"
        :disabled="chatStore.isProcessing || !inputText.trim()"
        class="px-4 py-2.5 bg-blue-500 text-white rounded-xl text-sm font-medium
               hover:bg-blue-600 disabled:bg-gray-300 disabled:cursor-not-allowed
               transition-colors shrink-0 cursor-pointer"
      >
        发送
      </button>
    </div>
  </div>
</template>
