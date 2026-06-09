"""服务配置"""

import os

# 服务地址
HOST = os.getenv("SERVER_HOST", "0.0.0.0")
PORT = int(os.getenv("SERVER_PORT", "8000"))

# CORS 允许的前端地址（Vite 默认 5173）
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")

# WebSocket 心跳间隔（秒）
WS_PING_INTERVAL = 30
