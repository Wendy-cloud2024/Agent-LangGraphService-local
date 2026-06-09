# 📌 简历项目展示：基于 LangGraph 的多智能体电商客服系统

> **项目名称**：thesis-agent —— 服装电商多 Agent 智能客服系统
> **技术栈**：Python 3.12 · LangGraph · LangChain · DeepSeek LLM · ChromaDB · SQLite · RAG (BM25 + Vector)
> **代码规模**：84 个 Python 源文件，~7,100 行代码

---

## 一、项目简介

基于 **LangGraph**（LangChain 官方图编排框架）构建的**多智能体（Multi-Agent）电商智能客服系统**。系统采用 **Supervisor 编排模式**，实现了一个覆盖售前咨询、售中订单、售后服务、投诉处理、通用问答五大业务场景的完整客服工作流。

系统不是简单的 LLM 对话封装，而是实现了**意图路由、多子图并行执行、人工审批断点、澄清回路、降级容错、安全审核闭环**等工业级能力。

---

## 二、系统架构

```
用户消息 → orchestrator_gate（8步入口关卡）
              ├── 安全审核 → 敏感词/极端情感旁路
              ├── 转人工快捷匹配（正则，零LLM延迟）
              ├── 多模态轻量预处理
              ├── 语言检测 + 对话摘要压缩
              ├── 意图分类 + 情感检测
              └── 多维路由决策
                      │
         ┌──── Send() 并行扇出 ────┐
         ↓          ↓         ↓         ↓         ↓
    售前Agent  售中Agent  售后Agent  投诉Agent  通用Agent
    (子图)     (子图)     (子图)     (子图)     (子图)
         └──── 结果聚合 fan-in ────┘
                      │
            subgraph_output_router（优先级路由）
              ├── escalate信号 → 中断其他子图
              ├── clarification → clarify_to_customer 旁路
              ├── fallback → 预置话术降级
              └── normal → content_merger → tone_adapter → output_gate
                                                        │
                                              三级风险路由（低/中/高）
                                              ├── 低风险 → 自动发送
                                              ├── 中风险 → 自动修正（最多1次）
                                              └── 高风险 → human_review（interrupt断点）
                                                              │
                                                    人工决策（5种）
                                              批准/编辑/拒绝-重生成/拒绝-重分诊/接管
```

---

## 三、核心技术亮点

### 🔥 亮点 1：多智能体并行编排（LangGraph Send API）

- 使用 LangGraph **`Send()` API** 实现多子图并行扇出（Fan-out），单条用户消息可同时路由到多个专业 Agent
- 通过 **`operator.add` Reducer** 自动聚合并行子图结果
- 引入 **`_turn_start_idx` 轮次隔离机制**，解决 Reducer 累积导致的跨轮数据泄露问题
- 统一输出路由器 `subgraph_output_router` 按 **escalate > clarification > fallback > normal** 四级优先级处理并行结果

> **面试话术**：实现了基于 LangGraph Send API 的多 Agent 并行执行框架，支持单条消息同时分发到多个专业子图处理，通过自定义 Reducer 和轮次索引机制解决并行聚合中的数据隔离问题。

---

### 🔥 亮点 2：完整的 Human-in-the-Loop 审批闭环

- 使用 LangGraph **`interrupt()`** 实现执行断点，支持高风险操作（退款、取消订单、补偿发放等）需人工审批
- 人工审核支持 **5 种决策**：批准、编辑、拒绝-重生成、拒绝-重分诊、接管会话
- **安全闭环设计**：人工编辑/批准后的内容必须再次通过 `output_gate` 质量关卡，防止内部信息泄露
- **防死循环机制**：`human_review_rounds` 计数器限制最多 2 轮审核，超过则强制转人工接管

> **面试话术**：基于 LangGraph interrupt() 实现了完整的人工审批断点机制，包含 5 种决策路径和安全闭环设计——即使人工编辑后的内容也必须再次通过自动质量关卡，确保不会泄露内部敏感信息。

---

### 🔥 亮点 3：澄清回路与多轮上下文恢复

- 实现了**澄清回路旁路**：子图缺少关键信息时（如订单号），通过 `clarify_to_customer` 节点直接向客户追问，绕过主流程（内容融合/语气适配/输出关卡）
- **状态挂起恢复**：通过 `pending_clarification` + `pending_subgraph` + `pending_accumulated_state` 三个状态字段，在客户回复后**直接路由回原子图**，跳过重复分诊
- 澄清最多 2 次，超过则自动转人工

> **面试话术**：设计了澄清回路旁路机制，子图缺少关键信息时可直接向用户追问，通过状态挂起和恢复机制在用户回复后精确路由回原始处理节点，避免重复分诊和信息丢失。

---

### 🔥 亮点 4：混合 RAG 检索系统（Vector + BM25 + RRF 融合）

- 实现了**向量检索 + BM25 关键词检索**的双路召回
- 向量检索使用 **ChromaDB** + DashScope `text-embedding-v4`（1024维）
- BM25 使用 **jieba 中文分词** + `rank-bm25` 库
- 两路结果通过 **Reciprocal Rank Fusion (RRF, k=60)** 融合排序
- 支持**全量/增量索引**，通过文件哈希追踪实现增量更新
- 检索源：6 份电商知识文档（FAQ、退换货政策、物流政策、支付政策、促销规则、保修政策）

> **面试话术**：自建了混合 RAG 检索系统，融合 ChromaDB 向量检索和 jieba+BM25 关键词检索，通过 RRF 融合排序算法合并双路召回结果，支持基于文件哈希的增量索引更新。

---

### 🔥 亮点 5：Supervisor 中断协议与降级容错

- 每个子图通过 `context_wrapper` 统一包装，提供 **30 秒超时保护 + 错误边界**
- 子图可发出 `escalate_signal`（`to_complaint` / `to_human`），Supervisor 据此**强制中断并行执行中的其他子图**
- 完整降级策略：超时 → 预置话术 + 后台告警；工具调用失败 → 重试 1 次后降级
- **投诉子图不可降级**：异常时直接转人工经理，确保投诉必须被处理

> **面试话术**：设计了 Supervisor 中断协议，子图可发出升级信号强制中断并行执行，同时实现了多层级降级容错——包括超时保护、工具重试、预置话术替换，而投诉场景强制不降级直接转人工。

---

### 🔥 亮点 6：四级记忆架构

| 层级 | 机制 | 作用 |
|------|------|------|
| L1 工作记忆 | 滑动窗口（20条消息） | 控制上下文长度 |
| L2 对话历史 | LangGraph Checkpointing | 会话级状态持久化 |
| L3 对话摘要 | LLM 摘要压缩（>16条触发） | 长对话压缩，保留关键信息 |
| L4 跨会话画像 | JSON 持久化 + SQLite 备份 | 客户偏好、历史问题、等级 |

> **面试话术**：实现了四级记忆架构——从工作记忆窗口、LangGraph Checkpointing 会话持久化，到 LLM 摘要压缩和跨会话客户画像，确保长对话和跨会话场景下上下文不丢失。

---

### 🔥 亮点 7：三级风险评估与自动修正

- `output_gate` 对所有输出进行**安全检查 + 质量评分 + 风险评估**
- **三级路由**：低风险自动发送 → 中风险自动修正（回环 tone_adapter，最多 1 次）→ 高风险人工审核
- 中风险修正后仍不通过 → **直接升级为高风险**，不自动发送
- 质量分 < 0.4 时触发从 `orchestrator_gate` 重新处理整个流程

> **面试话术**：设计了三级风险评估系统，结合安全检查、质量评分和风险定级，对 AI 输出进行分级处理——低风险自动发送、中风险自动修正（限1次）、高风险强制人工审核，修正失败直接升级，确保零高危险输出。

---

### 🔥 亮点 8：Session Takeover（会话接管）机制

- 人工客服可通过"接管"决策获取会话控制权
- 设置 `session_takeover = True` 后，该会话的**所有后续消息在 orchestrator_gate 入口处直接绕过 AI**，零延迟路由到人工
- 支持 `/end_takeover` 命令释放接管，恢复 AI 自动处理

> **面试话术**：实现了会话接管机制，人工客服可一键接管会话，接管后所有客户消息在系统入口即被拦截并路由到人工，完全绕过 AI 处理流程，保障人工服务时的响应零延迟。

---

## 四、技术细节补充

### LangGraph 核心特性全覆盖

| LangGraph 特性 | 本项目应用 |
|---|---|
| `StateGraph` | 监督者图 + 5 个子图，共 6 层图 |
| `add_conditional_edges()` | orchestrator 路由、output_gate 三级路由、子图输出分流 |
| Subgraphs | 5 个专业 Agent 作为编译子图 |
| Supervisor Pattern | 中央监督者编排 + 中断协议 |
| `interrupt()` + `Command(resume=...)` | 人工审核断点 + 工具审批门控 |
| Cycles/Loops | 澄清回路、自动修正循环、拒绝重生成循环 |
| Checkpointing | `MemorySaver` 会话持久化 |
| `Send()` fan-out | 多子图并行扇出 |
| `@tool` Tool Calling | 17 个电商工具 + 5 个视觉工具 |
| State Reducers | `operator.add` 聚合并行结果 |

### 工具体系（17 + 5 个）

| 风险等级 | 工具 | 数量 |
|---|---|---|
| **低风险** | 商品搜索、库存查询、订单详情、物流追踪、支付状态、知识库搜索、尺码推荐、退货资格、保修状态等 | 13 |
| **中风险** | 修改地址、发送退货面单、发放积分、重试支付 | 4 |
| **高风险** | 发放退款、取消订单、处理换货、发放补偿、资格覆盖（均需 interrupt 审批） | 5 |

### 数据库设计（SQLite，4 表）

- **products**：8 件服装商品，含 SKU、分类、价格、颜色、材质
- **product_details**：每 SKU 的尺码表（S/M/L/XL/XXL），含身高、体重、胸围、肩宽、腰围
- **customers**：5 个客户，含身高、体重、性别、手机、地址
- **orders**：10 个订单，含状态流转（待付款→已付款→已发货→已签收→取消/退款）

---

## 五、测试覆盖

| 测试模块 | 覆盖内容 | 用例数 |
|---|---|---|
| `test_clarify_and_quality.py` | 澄清回路状态管理 + 端到端 | 8 逻辑 + 1 e2e |
| `test_interrupt_takeover.py` | 升级协议 + 会话接管生命周期 | 14 逻辑 + 1 e2e |
| `test_parallel_execution.py` | 多 Agent 并行路由 + 结果聚合 | 逻辑 + e2e |
| `test_deepseek.py` | DeepSeek API 集成测试 | 7 集成测试 |

---

## 六、简历展示建议（精简版）

> **项目名称**：基于 LangGraph 的多 Agent 电商智能客服系统
>
> **技术栈**：Python · LangGraph · LangChain · DeepSeek · ChromaDB · SQLite · RAG
>
> **项目描述**：
> 基于 LangGraph 构建的 Supervisor 模式多 Agent 客服系统，覆盖售前/售中/售后/投诉/通用五大业务场景。实现了多子图并行编排、interrupt 断点人工审批、澄清回路、三级风险评估与自动修正、混合 RAG 检索、四级记忆架构、Supervisor 中断协议与降级容错等核心能力。系统包含 17 个电商工具（按风险分级管理）、6 层 StateGraph 编排、完整的安全审核闭环，代码规模约 7,000 行。
>
> **核心贡献**：
> - 基于 LangGraph Send API 实现多 Agent 并行扇出，通过自定义 Reducer 和轮次隔离机制解决并行聚合问题
> - 设计三级风险评估系统（自动发送/自动修正/人工审核），结合 interrupt() 实现完整人工审批闭环
> - 自建混合 RAG 检索（ChromaDB + BM25 + RRF 融合），支持增量索引
> - 实现四级记忆架构，涵盖工作记忆、会话持久化、LLM 摘要压缩、跨会话客户画像
> - 设计 Supervisor 中断协议，支持子图强制中断、多层级降级容错

---

## 七、作为简历项目的评价

### ✅ 优势

| 维度 | 评价 |
|---|---|
| **技术深度** | ⭐⭐⭐⭐⭐ 覆盖了 LangGraph 几乎所有核心特性（Send、interrupt、Reducer、Subgraph、Checkpointing），不是简单的 API 调用封装 |
| **架构复杂度** | ⭐⭐⭐⭐⭐ Supervisor + 5 子图 + 并行编排 + 优先级路由，体现系统设计能力 |
| **工程完整度** | ⭐⭐⭐⭐ 有完整的错误处理、降级策略、观测埋点、配置管理、测试覆盖 |
| **业务理解** | ⭐⭐⭐⭐ 贴近真实电商场景，有风险分级、人工审批、会话接管等实际需求 |
| **可展示性** | ⭐⭐⭐⭐ 架构图清晰，有端到端流程演示（human_sim 交互模拟器），面试时好讲 |

### ⚠️ 可提升的方向

| 方向 | 建议 | 优先级 |
|---|---|---|
| **前端界面** | 加一个简单的 Streamlit/Gradio Web 界面，面试时可以现场演示 | 🔴 高 |
| **性能指标** | 补充一些量化数据：响应延迟、准确率、并发处理量等 | 🔴 高 |
| **部署方案** | 加 Dockerfile + docker-compose，展示生产化意识 | 🟡 中 |
| **多轮评测** | 用真实对话数据做自动化评测（正确率/满意度），产出评估报告 | 🟡 中 |
| **真实视觉工具** | 当前视觉工具是 mock 实现，可接入真实 OCR/CV API 增加含金量 | 🟡 中 |
| **对话日志面板** | 做一个简单的 LangSmith/自定义 Dashboard 展示 trace 数据 | 🟢 锦上添花 |

### 📊 总评

**作为简历项目，这个项目的含金量是非常高的。** 具体来说：

1. **技术难度足够**：多 Agent 编排是当前 AI 工程的热门方向，LangGraph 是该领域的代表性框架。项目不是简单的"调 API 写个聊天机器人"，而是真正在做一个**有状态的多步骤工作流引擎**。

2. **面试故事性好**：每个技术亮点都有明确的"为什么这样做"（如澄清回路解决重复分诊、安全闭环防止信息泄露、中断协议处理紧急场景），适合在面试中展开讲述。

3. **覆盖面广**：涉及 Agent 编排、RAG 检索、状态管理、人机协作、容错降级、记忆系统等多个子系统，展示系统设计能力。

4. **对标工业级**：人工审核闭环、风险分级、降级策略、观测埋点、策略版本等设计，都体现了一定的工程素养。

**建议**：如果能在简历中附上一张清晰的架构图 + 几个关键数据指标（如"覆盖 18 种意图分类，支持 5 个并行子图，17 个工具按风险分级管理"），效果会更好。如果能做一个 **可交互的 Web Demo**，那就几乎无可挑剔了。

---

## 八、关键词索引（面试高频词）

`Multi-Agent` · `LangGraph` · `Supervisor Pattern` · `StateGraph` · `Send API` · `interrupt()` · `Human-in-the-Loop` · `Reducer` · `Fan-out/Fan-in` · `RAG` · `Hybrid Retrieval` · `BM25` · `ChromaDB` · `RRF` · `State Machine` · `Checkpointing` · `Tool Calling` · `Graceful Degradation` · `Circuit Breaker` · `Risk Assessment` · `Memory Architecture`
