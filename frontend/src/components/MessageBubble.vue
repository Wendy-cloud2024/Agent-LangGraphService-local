<script setup lang="ts">
import { computed } from 'vue'
import type { ChatMessageItem } from '@/types'

const props = defineProps<{
  message: ChatMessageItem
}>()

const isCustomer = computed(() => props.message.role === 'customer')
const isAgent = computed(() => props.message.role === 'agent')
const isSystem = computed(() => props.message.role === 'system')
</script>

<template>
  <!-- 客户消息: 右侧蓝色 -->
  <div v-if="isCustomer" class="flex justify-end">
    <div class="max-w-[75%] bg-blue-500 text-white rounded-2xl rounded-br-md px-4 py-2.5">
      <p class="whitespace-pre-wrap break-words">{{ message.content }}</p>
    </div>
  </div>

  <!-- Agent 消息: 左侧灰色 -->
  <div v-else-if="isAgent" class="flex justify-start gap-2">
    <div class="w-8 h-8 rounded-full bg-emerald-100 text-emerald-600
                flex items-center justify-center text-sm shrink-0 mt-1">🤖</div>
    <div class="max-w-[75%] bg-white border border-gray-200 rounded-2xl rounded-bl-md px-4 py-2.5 shadow-sm">
      <p class="text-gray-800 whitespace-pre-wrap break-words">{{ message.content }}</p>
      <!-- 元数据标签 -->
      <div v-if="message.metadata" class="mt-2 flex flex-wrap gap-1.5">
        <span v-if="message.metadata.emotion"
          class="inline-block px-1.5 py-0.5 text-xs rounded bg-purple-50 text-purple-600">
          😊 {{ message.metadata.emotion }}
        </span>
        <span v-if="message.metadata.risk_level"
          class="inline-block px-1.5 py-0.5 text-xs rounded bg-yellow-50 text-yellow-700">
          ⚠️ {{ message.metadata.risk_level }}
        </span>
        <span v-if="message.metadata.active_agents?.length"
          class="inline-block px-1.5 py-0.5 text-xs rounded bg-blue-50 text-blue-600">
          🔀 {{ message.metadata.active_agents.join(', ') }}
        </span>
      </div>
    </div>
  </div>

  <!-- 系统消息: 居中灰色 -->
  <div v-else-if="isSystem" class="flex justify-center">
    <div class="px-3 py-1.5 text-xs text-gray-400 bg-gray-100 rounded-full">
      {{ message.content }}
    </div>
  </div>
</template>
