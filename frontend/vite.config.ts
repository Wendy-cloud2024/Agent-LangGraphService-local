import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    tailwindcss(),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    },
  },
  server: {
    proxy: {
      // API 代理目标：通过环境变量 VITE_API_TARGET 配置
      // - 本地开发（无 Docker）: 默认 http://localhost:8000
      // - Docker 开发环境: docker-compose 中设为 http://backend:8000（Docker 服务名）
      //
      // 【为什么需要改？】
      // 在 Docker 中，每个容器有独立的网络命名空间
      // "localhost" 在容器内指向容器自身，不是宿主机
      // Docker Compose 会创建一个共享网络，容器之间通过"服务名"通信
      // 所以 frontend 容器访问 backend 容器要用 http://backend:8000
      '/api': process.env.VITE_API_TARGET || 'http://127.0.0.1:8000',
      '/ws': {
        target: (process.env.VITE_API_TARGET || 'http://127.0.0.1:8000').replace('http', 'ws'),
        ws: true,
      },
    },
  },
})
