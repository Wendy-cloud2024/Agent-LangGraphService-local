# thesis-agent 开发命令
# 使用: make <command>

.PHONY: dev dev-server dev-frontend install build clean help

# 同时启动后端 + 前端开发服务器
dev:
	@echo "启动开发环境..."
	@echo "后端: http://localhost:8000 (API文档: http://localhost:8000/docs)"
	@echo "前端: http://localhost:5173"
	$(MAKE) dev-server & $(MAKE) dev-frontend

# 启动 FastAPI 后端
dev-server:
	py -m src.server.run_server

# 启动 Vue 前端
dev-frontend:
	cd frontend && npm run dev

# 安装前后端依赖
install:
	pip install -e .
	cd frontend && npm install

# 构建前端
build:
	cd frontend && npm run build

# 清理构建产物
clean:
	rm -rf frontend/dist
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

help:
	@echo "可用命令:"
	@echo "  make dev          - 同时启动后端+前端开发服务器"
	@echo "  make dev-server   - 仅启动FastAPI后端 (http://localhost:8000)"
	@echo "  make dev-frontend - 仅启动Vue前端 (http://localhost:5173)"
	@echo "  make install      - 安装前后端依赖"
	@echo "  make build        - 构建前端生产版本"
	@echo "  make clean        - 清理构建产物"
