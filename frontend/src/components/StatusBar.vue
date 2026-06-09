<script setup lang="ts">
import { useSessionStore } from '@/stores/session'

const sessionStore = useSessionStore()
</script>

<template>
  <div class="flex items-center justify-between px-4 py-3 bg-white border-b border-gray-200 shrink-0">
    <div class="flex items-center gap-3">
      <!-- Logo -->
      <div class="w-8 h-8 rounded-lg bg-blue-500 text-white flex items-center justify-center text-sm font-bold">
        AI
      </div>
      <!-- 客户信息 -->
      <div>
        <div class="text-sm font-medium text-gray-800">
          {{ sessionStore.customerName }}
          <span class="text-xs text-gray-400 ml-1">{{ sessionStore.session?.customer_tier }}</span>
        </div>
        <div class="text-xs text-gray-400 truncate max-w-48">
          {{ sessionStore.session?.thread_id?.slice(0, 8) }}...
        </div>
      </div>
    </div>

    <div class="flex items-center gap-3">
      <!-- 接管模式徽章 -->
      <span v-if="sessionStore.sessionTakeover"
        class="px-2 py-1 text-xs font-medium rounded-full bg-orange-100 text-orange-700 animate-pulse">
        接管模式
      </span>

      <!-- 结束会话 -->
      <button
        @click="sessionStore.endSession()"
        class="text-xs text-gray-400 hover:text-red-500 transition-colors cursor-pointer"
      >
        结束会话
      </button>
    </div>
  </div>
</template>
