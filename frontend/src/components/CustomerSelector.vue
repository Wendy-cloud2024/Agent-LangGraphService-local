<script setup lang="ts">
import { useSessionStore } from '@/stores/session'

const sessionStore = useSessionStore()

async function selectCustomer(customerId: string) {
  await sessionStore.createSession(customerId)
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center p-6">
    <div class="w-full max-w-2xl">
      <!-- 标题 -->
      <div class="text-center mb-8">
        <h1 class="text-3xl font-bold text-gray-800 mb-2">🛍️ 电商智能客服 Agent</h1>
        <p class="text-gray-500">基于 LangGraph 的多 Agent 电商客服系统</p>
      </div>

      <!-- 客户选择卡片 -->
      <div class="bg-white rounded-2xl shadow-sm border border-gray-200 p-6">
        <h2 class="text-lg font-semibold text-gray-700 mb-4">选择客户开始对话</h2>

        <div v-if="sessionStore.customers.length === 0"
          class="text-center text-gray-400 py-8">加载中...</div>

        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <button
            v-for="c in sessionStore.customers"
            :key="c.customer_id"
            @click="selectCustomer(c.customer_id)"
            class="flex items-center gap-4 p-4 rounded-xl border border-gray-200
                   hover:border-blue-400 hover:bg-blue-50 transition-all
                   text-left group cursor-pointer"
          >
            <!-- 头像 -->
            <div class="w-12 h-12 rounded-full bg-blue-100 text-blue-600
                        flex items-center justify-center text-lg font-bold shrink-0
                        group-hover:bg-blue-200">
              {{ c.name?.charAt(0) ?? '?' }}
            </div>
            <!-- 信息 -->
            <div class="min-w-0">
              <div class="font-medium text-gray-800 truncate">{{ c.name }}</div>
              <div class="text-sm text-gray-400">{{ c.customer_id }}</div>
            </div>
          </button>
        </div>
      </div>

      <!-- 技术标签 -->
      <div class="text-center mt-6 space-x-2">
        <span class="inline-block px-2 py-1 text-xs rounded bg-green-100 text-green-700">LangGraph</span>
        <span class="inline-block px-2 py-1 text-xs rounded bg-purple-100 text-purple-700">Multi-Agent</span>
        <span class="inline-block px-2 py-1 text-xs rounded bg-orange-100 text-orange-700">FastAPI</span>
        <span class="inline-block px-2 py-1 text-xs rounded bg-emerald-100 text-emerald-700">Vue 3</span>
      </div>
    </div>
  </div>
</template>
