<script setup lang="ts">
import { ref } from 'vue'
import { useChatStore } from '@/stores/chat'

const chatStore = useChatStore()
const showEditBox = ref(false)
const editedResponse = ref('')
const feedback = ref('')

function submit(decision: 'approve' | 'edit' | 'reject_regenerate' | 'reject_reclassify' | 'takeover') {
  if (decision === 'edit' && showEditBox.value) {
    chatStore.submitHumanDecision('edit', feedback.value, editedResponse.value)
  } else if (decision === 'edit') {
    showEditBox.value = true
    return
  } else {
    chatStore.submitHumanDecision(decision, feedback.value)
  }
  reset()
}

function cancelEdit() {
  showEditBox.value = false
  editedResponse.value = ''
}

function reset() {
  showEditBox.value = false
  editedResponse.value = ''
  feedback.value = ''
}
</script>

<template>
  <div v-if="chatStore.humanReviewPending" class="border-t-2 border-orange-300 bg-orange-50 p-4">
    <!-- 标题 -->
    <div class="flex items-center gap-2 mb-3">
      <span class="text-lg">🔒</span>
      <h3 class="text-sm font-semibold text-orange-800">人工审核请求</h3>
      <span class="ml-auto text-xs text-orange-600">
        第 {{ chatStore.humanReviewPending.review_info.review_round }} / 2 轮
      </span>
    </div>

    <!-- 待审核内容 -->
    <div class="bg-white rounded-lg p-3 mb-3 border border-orange-200">
      <p class="text-sm text-gray-800 whitespace-pre-wrap mb-2">
        {{ chatStore.humanReviewPending.review_info.draft_response }}
      </p>
      <div class="flex flex-wrap gap-2 text-xs">
        <span class="px-2 py-0.5 rounded bg-red-100 text-red-700">
          风险: {{ chatStore.humanReviewPending.review_info.risk_level }}
        </span>
        <span class="px-2 py-0.5 rounded bg-yellow-100 text-yellow-700">
          质量: {{ (chatStore.humanReviewPending.review_info.quality_score * 100).toFixed(0) }}%
        </span>
        <span v-if="chatStore.humanReviewPending.review_info.human_review_reason"
          class="px-2 py-0.5 rounded bg-gray-100 text-gray-600">
          原因: {{ chatStore.humanReviewPending.review_info.human_review_reason }}
        </span>
      </div>
    </div>

    <!-- 编辑框 -->
    <div v-if="showEditBox" class="mb-3">
      <textarea
        v-model="editedResponse"
        rows="3"
        class="w-full rounded-lg border border-orange-300 px-3 py-2 text-sm
               focus:outline-none focus:border-orange-400 resize-none"
        placeholder="输入修改后的回复内容..."
      />
      <div class="flex gap-2 mt-1">
        <button @click="submit('edit')"
          class="px-3 py-1.5 text-xs bg-blue-500 text-white rounded-lg hover:bg-blue-600 cursor-pointer">
          确认编辑
        </button>
        <button @click="cancelEdit"
          class="px-3 py-1.5 text-xs bg-gray-200 text-gray-600 rounded-lg hover:bg-gray-300 cursor-pointer">
          取消
        </button>
      </div>
    </div>

    <!-- 反馈输入 -->
    <div class="mb-3">
      <input
        v-model="feedback"
        type="text"
        class="w-full rounded-lg border border-orange-200 px-3 py-2 text-sm
               focus:outline-none focus:border-orange-400"
        placeholder="反馈意见（可选）"
      />
    </div>

    <!-- 5种决策按钮 -->
    <div class="flex flex-wrap gap-2">
      <button @click="submit('approve')"
        class="px-3 py-2 text-xs font-medium bg-green-500 text-white rounded-lg
               hover:bg-green-600 transition-colors cursor-pointer">
        ✅ 批准
      </button>
      <button @click="submit('edit')"
        class="px-3 py-2 text-xs font-medium bg-blue-500 text-white rounded-lg
               hover:bg-blue-600 transition-colors cursor-pointer">
        ✏️ 编辑
      </button>
      <button @click="submit('reject_regenerate')"
        class="px-3 py-2 text-xs font-medium bg-yellow-500 text-white rounded-lg
               hover:bg-yellow-600 transition-colors cursor-pointer">
        🔄 拒绝-重生成
      </button>
      <button @click="submit('reject_reclassify')"
        class="px-3 py-2 text-xs font-medium bg-purple-500 text-white rounded-lg
               hover:bg-purple-600 transition-colors cursor-pointer">
        🔀 拒绝-重分诊
      </button>
      <button @click="submit('takeover')"
        class="px-3 py-2 text-xs font-medium bg-red-500 text-white rounded-lg
               hover:bg-red-600 transition-colors cursor-pointer">
        👤 接管
      </button>
    </div>
  </div>
</template>
