# =============================================================================
# 📚 frontend/Dockerfile — 前端多阶段构建
# =============================================================================
#
# 【前端在 Docker 中有两种运行模式】
#
# 1. 开发模式（dev）: 运行 Vite 开发服务器，支持热模块替换（HMR）
#    - 用于 docker-compose.yml（开发环境）
#    - 通过 --target dev 指定构建到这个阶段
#
# 2. 生产模式（production）: 先用 Node.js 构建出静态文件，再用 nginx 服务
#    - 用于 docker-compose.prod.yml（生产环境）
#    - 通过 --target production 指定构建到这个阶段
#    - 为什么用 nginx？nginx 是高性能 Web 服务器，专门服务静态文件
#      比 Node.js/Vite 高效得多，而且自带反向代理功能
#
# =============================================================================


# =============================================================================
# Stage 1: dev — 开发环境（Vite 热重载）
# =============================================================================
#
# node:22-alpine 是 Node.js 官方镜像的 Alpine Linux 版本
# Alpine Linux 极其精简（~5MB），比标准 Debian 镜像小 ~100MB
# -alpine 后缀的镜像通常用于生产环境，体积小、攻击面小
#
FROM node:22-alpine AS dev

WORKDIR /app

# 先复制依赖声明文件（层缓存优化，同后端 Dockerfile 的原理）
# package-lock.json 锁定确切版本，保证每次安装结果一致
COPY package.json package-lock.json* ./

# npm install: 安装 package.json 中声明的所有依赖
# 在开发阶段需要 devDependencies（如 Vite、TypeScript 编译器等）
RUN npm install

# 开发阶段不复制源码！源码通过 docker-compose.yml 的 volume 挂载进来
# 这样修改代码后 Vite 会自动检测并热更新，无需重新构建镜像
#
# 开发服务器命令在 docker-compose.yml 中通过 command 覆盖
# 默认命令只是占位
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
#                                          ^^^^^^^^^^^^^^
# --host 0.0.0.0: 让 Vite 监听所有网络接口
# 默认 Vite 只监听 localhost，在 Docker 中外部无法访问
# 加上这个才能从宿主机（你的浏览器）访问容器内的 Vite


# =============================================================================
# Stage 2: build — 构建生产版本
# =============================================================================
#
FROM node:22-alpine AS build

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci
# npm ci = Clean Install（干净安装）
# 与 npm install 的区别：
#   - 严格按照 package-lock.json 安装，不更新版本
#   - 先删除 node_modules 再安装，确保干净
#   - 速度更快，适合 CI/CD 和 Docker 构建场景

# 复制所有源代码（构建需要完整代码）
COPY . .

# npm run build: 执行 Vite 构建
# 输出静态文件到 dist/ 目录（HTML + JS + CSS）
RUN npm run build


# =============================================================================
# Stage 3: production — Nginx 服务生产版本
# =============================================================================
#
# nginx:alpine 是 Nginx 的 Alpine 版本，只有 ~7MB
# 专门用来服务静态文件和做反向代理
#
FROM nginx:alpine AS production

# 删除 nginx 默认配置（我们用自己的）
RUN rm /etc/nginx/conf.d/default.conf

# 复制我们自定义的 nginx 配置文件
# 这个文件定义了：静态文件服务、API 反向代理、WebSocket 代理
COPY nginx.conf /etc/nginx/conf.d/default.conf

# 从 build 阶段复制构建产物
# /usr/share/nginx/html/ 是 nginx 默认的静态文件目录
COPY --from=build /app/dist /usr/share/nginx/html

# Nginx 默认监听 80 端口
EXPOSE 80

# nginx 启动命令
# -g 'daemon off;': 让 nginx 在前台运行
# Docker 容器需要前台进程，如果主进程退出容器就会停止
CMD ["nginx", "-g", "daemon off;"]
