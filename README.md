# 🛒 Agent-LangGraphService-local：基于 LangGraph 的智能电商客服系统

> 面向实际业务场景的智能客服项目，支持持续迭代和功能扩展。

## 当前维护方向

- 调整项目命名、目录说明和本地运行文档
- 按实际业务补充商品、订单、售后等知识库内容
- 优化 Agent 路由、RAG 检索和人工审核流程
- 完善测试、错误处理和部署脚本

## 📖 项目简介

本系统是一个面向服装电商场景的**多 Agent 智能客服**，覆盖售前咨询、售中订单管理、售后支持、投诉处理和通用问答五大业务场景。系统采用 **LangGraph** 进行多 Agent 并行编排，通过 `Send` API 实现意图识别后的多子图并行扇出执行，并结合分级风险评估实现**人工审核闭环**（Human-in-the-Loop）。

### ✨ 核心特性

| 特性 | 说明 |
|------|------|
| **多 Agent 并行编排** | 基于 LangGraph `Send` API，5 个专业子图按意图并行扇出，`operator.add` Reducer 聚合结果 |
| **三级风险评估** | 低风险全自动、中风险自动修正、高风险触发 `interrupt()` 人工审核断点 |
| **人工审核闭环** | 5 种审核路径（批准/编辑/拒绝重生成/拒绝重分诊/接管），审核后内容须通过安全复查 |
| **澄清回路** | 子图可直接向客户追问，最多 2 轮后自动升级转人工 |
| **混合 RAG 检索** | ChromaDB 向量检索 + BM25 关键词检索 + RRF 融合排序（可选 Reranker 精排） |
| **4 层记忆架构** | 工作记忆 → 对话历史 → 对话摘要 → 跨会话客户画像 |
| **多模态支持** | 图片安全审核、商品视觉匹配、破损检测、OCR 运单识别等视觉工具 |
| **实时 WebSocket** | FastAPI + WebSocket 实时通信，前端即时展示 Agent 处理进度和审核面板 |

---

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        Customer Message                         │
└──────────────────────────┬──────────────────────────────────────┘
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│                     orchestrator_gate (入口关卡)                  │
│  ⓪ 澄清重入检查 → ① 安全审核 → ② 转人工匹配 → ③ 多模态预处理     │
│  → ④ 语言检测 → ⑤ 历史加载 → ⑥⑦ 意图+情感(单次LLM) → ⑧ 路由   │
└──────┬──────────┬──────────┬──────────┬──────────┬───────────────┘
       ▼          ▼          ▼          ▼          ▼    (并行扇出)
┌──────────┐┌──────────┐┌──────────┐┌──────────┐┌──────────┐
│ 售前Agent ││ 售中Agent ││ 售后Agent ││ 投诉Agent ││ 通用Agent │
│ 商品/库存 ││ 订单/物流 ││ 退换/保修 ││ 最高优先级││ FAQ/政策  │
└──────┬───┘└──────┬───┘└──────┬───┘└──────┬───┘└──────┬───┘
       └────────┴────────┴────────┴────────┘
                          ▼
              subgraph_output_router (优先级路由)
            ┌───── escalate → escalate_to_human
            ├───── clarification → clarify_to_customer
            └───── normal/fallback ↓
                          ▼
                  content_merger (内容融合)
                          ▼
                  tone_adapter (语气适配)
                          ▼
                output_gate (三级安全路由)
            ┌───── low → respond_to_customer ✅
            ├───── medium → 自动修正循环 (回到 tone_adapter)
            └───── high/critical → human_review (人工审核断点)
                          ▼
              ┌── approve/edit → output_gate (安全闭环)
              ├── reject_regenerate → content_merger
              ├── reject_reclassify → orchestrator_gate
              └── takeover → escalate_to_human
```

---

## 📁 项目结构

```
Agent-LangGraphService-local/
├── src/                              # 后端源码
│   ├── graph/                        # LangGraph 多 Agent 图
│   │   ├── supervisor.py             # 顶层监督者 StateGraph（核心编排）
│   │   ├── nodes/                    # 图节点
│   │   │   ├── orchestrator_gate.py  #   入口关卡（8 步处理流水线）
│   │   │   ├── subgraph_output_router.py  # 子图输出优先级路由器
│   │   │   ├── content_merger.py     #   内容融合器
│   │   │   ├── tone_adapter.py       #   语气与合规适配器
│   │   │   ├── output_gate.py        #   输出关卡（三级风险评估）
│   │   │   ├── human_review.py       #   人工审核断点（5 种决策路径）
│   │   │   ├── clarify_to_customer.py#   澄清追问旁路
│   │   │   ├── escalate_to_human.py  #   转人工客服
│   │   │   ├── respond_to_customer.py#   最终回复发送
│   │   │   └── context_wrapper.py    #   子图上下文注入包装器
│   │   └── subgraphs/                # 5 个专业 Agent 子图
│   │       ├── presales/             #   售前咨询（商品/库存/推荐/优惠）
│   │       ├── insales/              #   售中管理（订单/物流/支付/操作）
│   │       ├── aftersales/           #   售后支持（退换/退款/保修）
│   │       ├── complaint/            #   投诉处理（最高优先级，不降级）
│   │       └── general/              #   通用问答（FAQ/政策/情绪监控）
│   ├── state/                        # 状态 Schema
│   │   └── schema.py                 #   ConversationState + 6 种子图状态
│   ├── tools/                        # 工具集（22 个 @tool）
│   │   ├── ecommerce_tools.py        #   电商后端工具（低/中/高风险分级）
│   │   ├── vision_tools.py           #   多模态视觉工具
│   │   ├── context_injection.py      #   上下文注入工具
│   │   └── result_logger.py          #   结果记录工具
│   ├── rag/                          # RAG 混合检索系统
│   │   ├── pipeline/                 #   索引流水线
│   │   ├── retriever/                #   检索器（向量/BM25/混合/Reranker）
│   │   ├── embedder/                 #   嵌入器（OpenAI Embedding）
│   │   ├── store/                    #   向量存储（ChromaDB）
│   │   ├── loader/                   #   文档加载器（MD/DOCX/目录）
│   │   └── chunker/                  #   文本分块器
│   ├── memory/                       # 4 层记忆系统
│   │   └── customer_store.py         #   跨会话客户画像（JSON 持久化）
│   ├── server/                       # FastAPI 后端
│   │   ├── app.py                    #   应用工厂
│   │   ├── run_server.py             #   启动入口
│   │   ├── ws_handler.py             #   WebSocket 处理器（统一主循环）
│   │   ├── rest_routes.py            #   REST API 路由
│   │   ├── session_manager.py        #   会话管理器
│   │   ├── graph_manager.py          #   图编译与执行管理
│   │   ├── protocol.py               #   消息协议定义
│   │   └── config.py                 #   服务器配置
│   ├── db/                           # 数据库层
│   │   ├── connection.py             #   SQLite 连接
│   │   ├── queries.py                #   查询函数
│   │   └── seed.py                   #   种子数据
│   ├── config/                       # 配置
│   │   ├── settings.py               #   全局设置
│   │   ├── llm.py                    #   LLM 配置
│   │   └── prompts.py                #   Prompt 模板
│   └── utils/                        # 工具函数
│       ├── safety.py                 #   安全检查
│       ├── summarizer.py             #   对话摘要
│       ├── observability.py          #   可观测性
│       ├── parse.py                  #   解析工具
│       ├── escalation.py             #   升级逻辑
│       └── conversation.py           #   对话工具
├── frontend/                         # Vue 3 前端
│   ├── src/
│   │   ├── components/
│   │   │   ├── ChatWindow.vue        #   聊天窗口
│   │   │   ├── MessageBubble.vue     #   消息气泡
│   │   │   ├── MessageInput.vue      #   消息输入框
│   │   │   ├── HumanReviewPanel.vue  #   人工审核面板
│   │   │   ├── CustomerSelector.vue  #   客户选择器
│   │   │   ├── StatusBar.vue         #   状态栏
│   │   │   └── AgentMetadata.vue     #   Agent 元数据展示
│   │   ├── stores/                   #   Pinia 状态管理
│   │   │   ├── chat.ts               #   聊天状态
│   │   │   └── session.ts            #   会话状态
│   │   ├── api/
│   │   │   └── websocket.ts          #   WebSocket 通信
│   │   ├── types/
│   │   │   └── index.ts              #   TypeScript 类型定义
│   │   └── utils/
│   │       └── mock-ws.ts            #   演示模式 Mock WebSocket
│   └── package.json
├── data/                             # 数据目录
│   ├── ecommerce.db                  #   SQLite 数据库
│   ├── knowledge/                    #   知识库文档
│   │   ├── faq.md                    #     常见问题
│   │   ├── return_policy.md          #     退货政策
│   │   ├── shipping_policy.md        #     物流政策
│   │   ├── payment_policy.md         #     支付政策
│   │   ├── warranty_policy.md        #     保修政策
│   │   └── promotion_rules.md        #     促销规则
│   └── customers/                    #   客户画像 JSON
├── tests/                            # 测试套件
│   ├── test_parallel_execution.py    #   并行执行测试
│   ├── test_interrupt_takeover.py    #   中断与接管测试
│   ├── test_clarify_and_quality.py   #   澄清回路与质量测试
│   └── test_deepseek.py              #   DeepSeek 模型测试
├── human_sim/                        # 人工模拟器（自动化测试）
│   └── simulator.py
├── pyproject.toml                    # Python 项目配置
├── Makefile                          # 开发命令
├── .env.example                      # 环境变量模板
└── .gitignore
```

---

## 🛠️ 技术栈

| 层级 | 技术 |
|------|------|
| **AI 框架** | LangGraph (多 Agent 编排) + LangChain |
| **LLM 模型** | OpenAI GPT / Anthropic Claude / DeepSeek |
| **后端** | Python 3.12 + FastAPI + Uvicorn |
| **前端** | Vue 3 + TypeScript + Vite + Pinia + Tailwind CSS |
| **数据库** | SQLite (业务数据) + ChromaDB (向量存储) |
| **RAG** | ChromaDB + BM25 (jieba 中文分词) + RRF 融合 |
| **实时通信** | WebSocket (FastAPI) |
| **可观测性** | LangSmith Tracing + 自定义日志 |
| **多模态** | 图片审核/商品匹配/破损检测/OCR 运单 |

---

## 🚀 快速开始

### 前置要求

- **Python** >= 3.12
- **Node.js** >= 20.19（或 >= 22.12）
- **LLM API Key**（OpenAI / Anthropic / DeepSeek 至少一项）

### 1. 克隆项目

```bash
git clone https://github.com/Wendy-cloud2024/Agent-LangGraphService-local.git
cd Agent-LangGraphService-local
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 填入你的 API Key
```

关键环境变量：

```env
# LLM API（至少配置一个）
OPENAI_API_KEY=sk-xxx
ANTHROPIC_API_KEY=sk-ant-xxx

# LangSmith 追踪（可选）
LANGCHAIN_TRACING_V2=true
LANGSMITH_API_KEY=lsv2-xxx

# RAG 向量嵌入
RAG_ZHIPU_API_KEY=xxx
```

### 3. 安装依赖

```bash
# 后端依赖
pip install -e .

# 前端依赖
cd frontend && npm install && cd ..
```

或使用 Make 一键安装：

```bash
make install
```

### 4. 启动开发服务器

```bash
# 同时启动后端 + 前端
make dev
```

或分别启动：

```bash
make dev-server    # 仅后端 → http://localhost:8000
make dev-frontend  # 仅前端 → http://localhost:5173
```

启动后访问：
- **前端界面**：http://localhost:5173
- **API 文档**：http://localhost:8000/docs
- **WebSocket**：`ws://localhost:8000/ws/{thread_id}`

---

## 📡 API 接口

### REST API

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/customers` | 获取客户列表 |
| `GET` | `/api/customers/{id}` | 获取客户详情 |
| `POST` | `/api/sessions` | 创建新会话 |
| `GET` | `/api/sessions` | 获取活跃会话列表 |
| `GET` | `/api/sessions/{id}/status` | 获取会话状态 |
| `POST` | `/api/sessions/{id}/end` | 结束会话 |

### WebSocket 协议

连接地址：`ws://localhost:8000/ws/{thread_id}`

**客户端 → 服务端：**

```json
{ "type": "chat", "content": "你好，我想查询订单" }
{ "type": "human_decision", "decision": "approve", "feedback": "", "edited_response": "" }
{ "type": "approval", "approved": true, "note": "同意" }
{ "type": "end_takeover" }
{ "type": "get_status" }
```

**服务端 → 客户端：**

```json
{ "type": "node_progress", "node": "presales_agent", "tags": { ... } }
{ "type": "agent_response", "content": "...", "sources": [...] }
{ "type": "human_review_request", "reason": "高风险操作需人工确认", "draft_response": "..." }
{ "type": "approval_request", "reason": "投诉补偿审批" }
{ "type": "clarification_request", "question": "请问您的订单号是多少？" }
{ "type": "escalated", "reason": "已转接人工客服" }
```

---

## 🧩 核心模块详解

### 多 Agent 并行编排

系统使用 LangGraph 的 `Send` API 实现意图识别后的多子图并行执行。当客户消息涉及多个业务场景时（如"我买了商品想退货，还想查物流"），系统会同时激活多个子图并行处理，结果通过 `operator.add` Reducer 聚合：

```python
# supervisor.py — 并行扇出路由
def route_by_labels(state):
    if len(active_agents) > 1:
        return [Send(agent, state) for agent in active_agents]  # 并行
    return active_agents[0]  # 单子图
```

### 三级风险评估 & 人工审核

所有 AI 回复在发送前必须通过 `output_gate` 的安全检查：

| 风险等级 | 处理方式 | 示例 |
|----------|----------|------|
| **Low** | 全自动发送 | 商品查询、物流追踪 |
| **Medium** | 自动修正循环（最多 1 次） | 语气不当、信息不完整 |
| **High** | `interrupt()` 触发人工审核 | 退款、取消订单、补偿 |
| **Critical** | 直接转人工 | 安全威胁、敏感信息 |

### 工具风险分级（22 个工具）

| 等级 | 数量 | 工具 |
|------|------|------|
| 🟢 低风险 | 13 | 商品搜索、库存查询、订单查询、物流追踪、支付状态、知识库检索、尺码推荐、退货资格检查... |
| 🟡 中风险 | 4 | 修改地址、退货标签、积分发放、支付重试 |
| 🔴 高风险 | 5 | 退款、取消订单、换货、补偿发放、政策例外审批 |

### 4 层记忆架构

| 层级 | 类型 | 实现 | 用途 |
|------|------|------|------|
| L1 | 工作记忆 | 滑动窗口（最近 20 条消息） | 当前对话上下文 |
| L2 | 对话历史 | LangGraph Checkpointing | 会话内完整状态持久化 |
| L3 | 对话摘要 | LLM 压缩（>16 条消息触发） | 长对话精简 |
| L4 | 跨会话画像 | JSON 文件 + SQLite 备份 | 客户偏好、历史、等级 |

### 混合 RAG 检索

```
Query → [ChromaDB 向量检索] ──→ RRF 融合 → [Reranker 精排] → Top-K 结果
      → [BM25 关键词检索]  ──↗
```

- **向量检索**：OpenAI Embedding + ChromaDB 存储
- **关键词检索**：jieba 中文分词 + rank-bm25
- **融合排序**：Reciprocal Rank Fusion (RRF, k=60)
- **可选精排**：bge-reranker-v2-m3
- **知识库**：6 份政策文档（FAQ、退货、物流、支付、保修、促销）

---

## 🧪 测试

```bash
# 并行执行测试
python tests/test_parallel_execution.py

# 中断与接管测试
python tests/test_interrupt_takeover.py

# 澄清回路与质量测试
python tests/test_clarify_and_quality.py
```

---

## 📦 Make 命令

```bash
make help            # 查看所有可用命令
make install         # 安装前后端依赖
make dev             # 同时启动后端+前端开发服务器
make dev-server      # 仅启动 FastAPI 后端 (http://localhost:8000)
make dev-frontend    # 仅启动 Vue 前端 (http://localhost:5173)
make build           # 构建前端生产版本
make clean           # 清理构建产物
```

---

## 📊 数据模型

### SQLite 数据库表

| 表 | 说明 | 数据量 |
|----|------|--------|
| `products` | 商品信息（SKU、名称、类别、价格、颜色、材质） | 8 件服装 |
| `product_details` | 尺码表（SKU 对应的身高/体重/胸围等数据） | 多尺码 |
| `customers` | 客户信息（身高、体重、联系方式） | 5 位客户 |
| `orders` | 订单（状态流转：pending → paid → shipped → delivered/cancelled） | 10 笔订单 |

### 种子数据初始化

```bash
python -m src.db.seed
```

---

## ⚙️ 配置说明

所有配置通过 `.env` 文件管理，参考 `.env.example`：

| 变量 | 说明 | 必填 |
|------|------|------|
| `OPENAI_API_KEY` | OpenAI API Key | 至少一项 |
| `ANTHROPIC_API_KEY` | Anthropic API Key | 至少一项 |
| `LANGCHAIN_API_KEY` | LangSmith 追踪 | 否 |
| `LANGCHAIN_TRACING_V2` | 启用 LangSmith 追踪 | 否 |
| `RAG_ZHIPU_API_KEY` | RAG 向量嵌入 API Key | 是 |
| `DATABASE_URL` | 数据库连接 URL | 否（默认 SQLite） |

---

## 📄 License

MIT License

---

## 🙏 致谢

- [LangGraph](https://github.com/langchain-ai/langgraph) — 多 Agent 编排框架
- [LangChain](https://github.com/langchain-ai/langchain) — LLM 应用开发框架
- [FastAPI](https://fastapi.tiangolo.com/) — 高性能 Python Web 框架
- [Vue.js](https://vuejs.org/) — 渐进式 JavaScript 框架
- [ChromaDB](https://www.trychroma.com/) — 开源向量数据库
