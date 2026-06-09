<script setup lang="ts">
import { ref, nextTick, watch, onMounted } from 'vue'
import { useSessionStore } from '@/stores/session'
import { useChatStore } from '@/stores/chat'
import StatusBar from '@/components/StatusBar.vue'
import MessageBubble from '@/components/MessageBubble.vue'
import MessageInput from '@/components/MessageInput.vue'
import HumanReviewPanel from '@/components/HumanReviewPanel.vue'
import AgentMetadata from '@/components/AgentMetadata.vue'
import {
  simulateNormalChat,
  simulateHumanReview,
  simulateApproveAfterReview,
  simulateClarification,
  simulateComplaintApproval,
} from '@/utils/mock-ws'

const props = defineProps<{ demoMode?: boolean }>()

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

// ==================== 演示模式 ====================

onMounted(() => {
  if (props.demoMode) {
    // 注册演示回调 — 人工决策后用模拟数据继续流程
    chatStore.enableDemoMode(
      // onHumanDecision
      async (decision: string, _feedback: string, _editedResponse: string) => {
        await simulateApproveAfterReview((e) => chatStore.handleServerEvent(e))
      },
      // onApproval
      async (_approved: boolean, _note: string) => {
        await simulateApproveAfterReview((e) => chatStore.handleServerEvent(e))
      },
    )
  }
})

async function demoNormal() {
  chatStore.clearMessages()
  chatStore.handleServerEvent({ type: 'node_progress', node: '__thinking__', tags: {} })
  _addCustomerMessage('你好，请问这款T恤有什么颜色和尺码？')
  await simulateNormalChat((e) => chatStore.handleServerEvent(e))
}

async function demoHumanReview() {
  chatStore.clearMessages()
  chatStore.handleServerEvent({ type: 'node_progress', node: '__thinking__', tags: {} })
  _addCustomerMessage('我买的衣服质量太差了，要求全额退款加赔偿！')
  await simulateHumanReview((e) => chatStore.handleServerEvent(e))
}

async function demoClarification() {
  chatStore.clearMessages()
  chatStore.handleServerEvent({ type: 'node_progress', node: '__thinking__', tags: {} })
  _addCustomerMessage('我要退货')
  await simulateClarification((e) => chatStore.handleServerEvent(e))
}

async function demoComplaint() {
  chatStore.clearMessages()
  chatStore.handleServerEvent({ type: 'node_progress', node: '__thinking__', tags: {} })
  _addCustomerMessage('我要投诉！你们是骗子！商品完全是假货！')
  await simulateComplaintApproval((e) => chatStore.handleServerEvent(e))
}

let _demoMsgId = 1000
function _addCustomerMessage(content: string) {
  chatStore.messages.push({
    id: `demo-${++_demoMsgId}`,
    role: 'customer',
    content,
    timestamp: Date.now(),
  })
}
</script>

<template>
  <div class="flex flex-col h-screen max-w-3xl mx-auto">
    <!-- 顶部状态栏 -->
    <StatusBar />

    <!-- 演示模式工具栏 -->
    <div v-if="demoMode" class="border-b border-amber-200 bg-amber-50 px-4 py-2 shrink-0">
      <div class="flex items-center gap-2 flex-wrap">
        <span class="text-xs font-medium text-amber-700">🎭 演示模式</span>
        <button @click="demoNormal"
          class="px-2 py-1 text-xs rounded bg-green-100 text-green-700 hover:bg-green-200 cursor-pointer transition-colors">
          💬 正常对话
        </button>
        <button @click="demoHumanReview"
          class="px-2 py-1 text-xs rounded bg-red-100 text-red-700 hover:bg-red-200 cursor-pointer transition-colors">
          🔒 人工审核
        </button>
        <button @click="demoClarification"
          class="px-2 py-1 text-xs rounded bg-blue-100 text-blue-700 hover:bg-blue-200 cursor-pointer transition-colors">
          ❓ 澄清回路
        </button>
        <button @click="demoComplaint"
          class="px-2 py-1 text-xs rounded bg-purple-100 text-purple-700 hover:bg-purple-200 cursor-pointer transition-colors">
          📢 投诉审批
        </button>
      </div>
    </div>

    <!-- 消息列表 -->
    <div ref="messagesContainer" class="flex-1 overflow-y-auto px-4 py-4 space-y-3">
      <!-- 无消息提示 -->
      <div v-if="chatStore.messages.length === 0 && !chatStore.isProcessing"
        class="text-center py-12">
        <p v-if="demoMode" class="text-gray-400 text-sm">点击上方按钮查看不同场景的 UI 表现</p>
      </div>

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
