<script setup lang="ts">
import { ref } from 'vue'
import { useChatStore } from '@/stores/chat'

const chatStore = useChatStore()
const expanded = ref(false)

function toggle() {
  expanded.value = !expanded.value
}
</script>

<template>
  <div class="border-t border-gray-100 bg-gray-50">
    <!-- 折叠标题 -->
    <button
      @click="toggle"
      class="w-full flex items-center justify-between px-4 py-2 text-xs text-gray-500
             hover:bg-gray-100 transition-colors cursor-pointer"
    >
      <span>📊 Agent 元数据</span>
      <span>{{ expanded ? '▲' : '▼' }}</span>
    </button>

    <!-- 展开内容 -->
    <div v-if="expanded && chatStore.lastAgentMetadata" class="px-4 pb-3 space-y-2">
      <div class="grid grid-cols-2 sm:grid-cols-3 gap-2 text-xs">
        <!-- 意图 -->
        <div v-if="chatStore.lastAgentMetadata.intent_labels?.length" class="col-span-2 sm:col-span-3">
          <span class="text-gray-400">意图:</span>
          <span
            v-for="label in chatStore.lastAgentMetadata.intent_labels"
            :key="label.intent"
            class="ml-1.5 px-1.5 py-0.5 rounded bg-blue-50 text-blue-600"
          >
            {{ label.intent }} ({{ (label.confidence * 100).toFixed(0) }}%)
          </span>
        </div>

        <!-- 情感 -->
        <div>
          <span class="text-gray-400">情感:</span>
          <span class="ml-1 text-purple-600">{{ chatStore.lastAgentMetadata.emotion }}</span>
        </div>

        <!-- 紧急度 -->
        <div>
          <span class="text-gray-400">紧急度:</span>
          <span class="ml-1" :class="{
            'text-red-600': chatStore.lastAgentMetadata.urgency === 'high' || chatStore.lastAgentMetadata.urgency === 'critical',
            'text-yellow-600': chatStore.lastAgentMetadata.urgency === 'medium',
            'text-green-600': chatStore.lastAgentMetadata.urgency === 'low',
          }">{{ chatStore.lastAgentMetadata.urgency }}</span>
        </div>

        <!-- 路由原因 -->
        <div v-if="chatStore.lastAgentMetadata.routing_reason" class="col-span-2 sm:col-span-3">
          <span class="text-gray-400">路由:</span>
          <span class="ml-1 text-blue-600">{{ chatStore.lastAgentMetadata.routing_reason }}</span>
        </div>

        <!-- 风险等级 -->
        <div>
          <span class="text-gray-400">风险:</span>
          <span class="ml-1 font-medium" :class="{
            'text-red-600': chatStore.lastAgentMetadata.risk_level === 'high' || chatStore.lastAgentMetadata.risk_level === 'critical',
            'text-yellow-600': chatStore.lastAgentMetadata.risk_level === 'medium',
            'text-green-600': chatStore.lastAgentMetadata.risk_level === 'low',
          }">{{ chatStore.lastAgentMetadata.risk_level }}</span>
        </div>

        <!-- 质量评分 -->
        <div>
          <span class="text-gray-400">质量:</span>
          <span class="ml-1 font-medium" :class="{
            'text-green-600': chatStore.lastAgentMetadata.quality_score >= 0.8,
            'text-yellow-600': chatStore.lastAgentMetadata.quality_score >= 0.5,
            'text-red-600': chatStore.lastAgentMetadata.quality_score < 0.5,
          }">{{ (chatStore.lastAgentMetadata.quality_score * 100).toFixed(0) }}%</span>
        </div>

        <!-- 解决状态 -->
        <div>
          <span class="text-gray-400">状态:</span>
          <span class="ml-1 text-gray-700">{{ chatStore.lastAgentMetadata.resolution_status }}</span>
        </div>
      </div>
    </div>
  </div>
</template>
