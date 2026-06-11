# =============================================================================
# 📚 Dockerfile — 后端镜像构建文件
# =============================================================================
#
# 【什么是 Dockerfile？】
# Dockerfile 是一个文本文件，包含了一条条指令（instruction），每条指令
# 对应镜像中的一层（layer）。Docker 按 从上到下 的顺序执行这些指令，
# 最终构建出一个可运行的镜像（image）。
#
# 【什么是镜像（Image）？】
# 镜像是一个只读的模板，包含了运行应用所需的一切：代码、运行时、库、
# 环境变量、配置文件。你可以把镜像理解为"安装包"。
#
# 【什么是容器（Container）？】
# 容器是镜像的运行实例。一个镜像可以启动多个容器。
# 类比：镜像是类（class），容器是实例（instance）。
#
# 【本 Dockerfile 采用"多阶段构建"（Multi-stage Build）】
# 分为两个阶段：
#   Stage 1 (builder): 安装所有 Python 依赖（包含编译工具等）
#   Stage 2 (runtime): 只复制安装好的依赖 + 项目代码，体积更小更安全
# 好处：最终镜像不包含 pip 缓存和编译工具，体积减少 50% 以上
#
# =============================================================================


# =============================================================================
# Stage 1: builder — 安装 Python 依赖
# =============================================================================
#
# 【FROM 指令】指定基础镜像，类似于 "继承"
# python:3.12-slim 是官方 Python 镜像的精简版：
#   - 基于 Debian，但去除了非必要软件（apt 包、文档等）
#   - 比 python:3.12 完整版小约 400MB
#   - 包含 pip，足够安装 Python 包
# AS builder 给这个阶段起名为 "builder"，后面用 COPY --from=builder 引用
#
FROM python:3.12-slim AS builder

# 【WORKDIR 指令】设置工作目录（类似 cd 命令）
# 所有后续的 RUN、CMD、COPY、ADD 指令都在这个目录下执行
# 如果目录不存在，Docker 会自动创建
# 这里设为 /app，与项目根目录对应
# 这样源码中的 Path(__file__).resolve().parent.parent.parent 会正确解析为 /app
#
WORKDIR /app

# 【COPY 指令】将文件从宿主机（你的电脑）复制到镜像中
# 格式：COPY <宿主机路径> <镜像内路径>
#
# 【层缓存优化】先只复制 pyproject.toml！
# Docker 镜像是分层的，每一层都有缓存。如果某一层发生变化，它和后续
# 所有层都会重新构建。
#
# 依赖变化少，代码变化多。如果先复制所有代码再 pip install：
#   修改任何 .py 文件 → COPY 层变化 → pip install 层缓存失效 → 重新安装所有包！
#
# 正确做法：先复制 pyproject.toml → pip install → 再复制代码
# 这样只有 pyproject.toml 变了才会重新安装依赖（通常很少变）
# 代码变了只影响后面的 COPY 层，pip install 使用缓存，快很多！
#
COPY pyproject.toml .

# 【RUN 指令】在镜像构建时执行命令
# --no-cache-dir: 不缓存下载的包，减小镜像体积
# -e .: 以"可编辑模式"安装项目（即安装依赖但不复制代码，因为代码还没 COPY 进来）
#       这里只用来安装 pyproject.toml 中声明的依赖
#
RUN pip install --no-cache-dir -e .

# =============================================================================
# Stage 2: runtime — 最终运行时镜像
# =============================================================================
#
# 再次 FROM 一个全新的基础镜像，不继承 builder 的中间层
# 这样最终镜像只有 runtime 阶段的层，不包含 builder 的 pip 缓存等
#
FROM python:3.12-slim AS runtime

# 【RUN 安装系统级依赖】
# curl: 用于后面的 HEALTHCHECK 健康检查
# sqlite3: 用于调试时查看数据库（可选）
# --no-install-recommends: 不安装 apt 推荐的非必要包，减小体积
# && rm -rf /var/lib/apt/lists/*: 清理 apt 缓存，减小镜像体积
#
RUN apt-get update && \
    apt-get install --no-install-recommends -y \
        curl \
        sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# 【从 builder 阶段复制已安装的 Python 包】
# COPY --from=<阶段名> 复制其他阶段的文件
# builder 阶段 pip install 把包装到了 /usr/local/lib/python3.12/site-packages/
# 复制这些已编译好的包，不需要在 runtime 阶段重新安装
#
COPY --from=builder /usr/local/lib/python3.12/site-packages/ /usr/local/lib/python3.12/site-packages/
COPY --from=builder /usr/local/bin/ /usr/local/bin/

# 【复制项目代码】
# 注意顺序：先复制依赖（上面），再复制代码（这里）
# 这样代码变化时不会使依赖安装层的缓存失效
#
# 复制后端源码
COPY src/ src/

# 复制项目配置
COPY pyproject.toml .

# 复制知识库文档（种子数据，RAG 系统需要）
# 这些是静态的 markdown 文件，构建时打入镜像
# 运行时数据（数据库、客户画像）通过 Volume 持久化，不在镜像中
COPY data/knowledge/ data/knowledge/

# 【创建运行时需要的目录】
# - data/: SQLite 数据库存放目录（数据库文件通过 seed.py 初始化）
# - data/customers/: 客户画像 JSON 文件目录
# - .chroma_db/: ChromaDB 向量数据库目录（RAG 索引时生成）
# - index/: BM25 索引缓存目录
# 这些目录在容器首次运行时为空，数据通过 Volume 持久化
#
RUN mkdir -p data data/customers .chroma_db index

# 【ENV 指令】设置环境变量（在镜像中持久存在）
# PYTHONUNBUFFERED=1: 禁用 Python 输出缓冲
#   没有这个设置，print() 和 logging 的输出可能会延迟
#   设置后日志实时输出，方便 docker logs 查看
#
ENV PYTHONUNBUFFERED=1

# 【EXPOSE 指令】声明容器监听的端口
# ⚠️ 注意：EXPOSE 只是一个文档说明，并不会真正发布端口！
# 真正的端口映射在 docker run -p 或 docker-compose 的 ports 中配置
# 就像在代码里写注释说"这个函数返回 int"，但注释本身不会改变运行行为
#
EXPOSE 8000

# 【HEALTHCHECK 指令】定义健康检查命令
# Docker 会定期运行这个命令，判断容器是否健康
# --interval=30s: 每 30 秒检查一次
# --timeout=10s: 10 秒内没响应视为失败
# --start-period=30s: 容器启动后 30 秒内不检查（给应用启动时间）
# --retries=3: 连续 3 次失败才标记为 unhealthy
#
# 检查方式：curl 访问 /api/customers 接口，成功则说明服务正常
#
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/api/customers || exit 1

# 【CMD 指令】容器启动时执行的默认命令
# 每个 Dockerfile 只能有一个 CMD（如果有多个，只有最后一个生效）
# 这里启动 FastAPI 服务器
# 注意：生产环境不用 --reload（热重载），开发环境在 docker-compose 中覆盖此命令
#
CMD ["python", "-m", "src.server.run_server"]
