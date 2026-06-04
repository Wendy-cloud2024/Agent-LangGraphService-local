"""
顶层监督者 StateGraph

组装完整的监督者图:
  orchestrator_gate → [子图并行扇出] → subgraph_output_router
  → content_merger → tone_adapter → output_gate
  → respond_to_customer | human_review | escalate_to_human

包含:
- 图节点注册
- 条件边定义 (route_by_labels, three_way_route, route_after_subgraph)
- 检查点配置 (MemorySaver/DatabaseCheckpointer)
- 子图编译与挂载
"""

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from src.state.schema import ConversationState
from src.graph.nodes.orchestrator_gate import orchestrator_gate, route_by_labels
from src.graph.nodes.respond_to_customer import respond_to_customer
from src.graph.nodes.escalate_to_human import escalate_to_human
from src.graph.nodes.content_merger import content_merger
from src.graph.nodes.tone_adapter import tone_adapter
from src.graph.nodes.output_gate import output_gate, three_way_route
from src.graph.nodes.subgraph_output_router import subgraph_output_router, route_after_output_router
from src.graph.nodes.clarify_to_customer import clarify_to_customer
from src.graph.nodes.human_review import human_review, route_after_human_review


def build_supervisor_graph() -> StateGraph:
    """构建完整的监督者图"""
    graph = StateGraph(ConversationState)

    # ==================== 注册节点 ====================

    # 【入口关卡】orchestrator_gate
    # 统一入口，执行8步处理流程:
    #   ⓪ pending_clarification前置检查 → 是则跳过全部分诊直接路由回原子图
    #   ① 安全审核（敏感词 + 图片合规）→ 不通过则旁路到complaint_agent或标记
    #   ② 转人工快捷匹配（正则匹配"人工客服/转人工/真人"等，零延迟不经LLM）
    #   ③ 多模态轻量预处理（仅通用图片描述，不做OCR/破损判定等专项）
    #   ④ 语言检测（中英文比例判断）
    #   ⑤ 轻量历史加载（最近3轮摘要）
    #   ⑥ 多维标签分类 → intent_labels（单次LLM调用合并⑥⑦）
    #   ⑦ 情感检测 + 紧急度
    #   ⑧ 路由决策 → active_agents（支持多子图并行扇出）
    graph.add_node("orchestrator_gate", orchestrator_gate)

    # 【子图节点】5个专业Agent子图，由orchestrator_gate按意图路由激活
    from src.graph.subgraphs.presales.graph import compile_presales_subgraph
    from src.graph.subgraphs.insales.graph import compile_insales_subgraph
    from src.graph.subgraphs.aftersales.graph import compile_aftersales_subgraph
    from src.graph.subgraphs.complaint.graph import compile_complaint_subgraph
    from src.graph.subgraphs.general.graph import compile_general_subgraph
    from src.graph.nodes.context_wrapper import create_subgraph_node

    # 售前子图: 商品查询/库存查询/推荐/优惠匹配, 含visual_product_match专项视觉工具
    graph.add_node("presales_agent", create_subgraph_node("presales_agent", compile_presales_subgraph()))
    # 售中子图: 订单查询/物流追踪/支付信息/操作执行, 含ocr_shipping_label专项视觉工具
    graph.add_node("insales_agent", create_subgraph_node("insales_agent", compile_insales_subgraph()))
    # 售后子图: 退换货/退款/保修, 含detect_product_damage + ocr_product_label专项视觉工具
    graph.add_node("aftersales_agent", create_subgraph_node("afters_agent", compile_aftersales_subgraph()))
    # 投诉子图: 最高优先级, 不降级, 异常直接escalate_to_human, 含detect_quality_issue
    graph.add_node("complaint_agent", create_subgraph_node("complaint_agent", compile_complaint_subgraph()))
    # 通用子图: FAQ/政策问答, 含emotion_monitor可发出escalate_to_complaint信号
    graph.add_node("general_agent", create_subgraph_node("general_agent", compile_general_subgraph()))

    # 【中间处理节点】
    # 子图输出统一路由器: 按优先级依次检查所有子图输出
    #   优先级1: escalate信号 → 中断其他并行子图, 路由到complaint_agent或escalate_to_human
    #   优先级2: clarification_request → 路由到clarify_to_customer（忽略其他子图正常结果）
    #            澄清次数≥2 → 路由到escalate_to_human
    #   优先级3: fallback标记 → 不单独路由, 标记后在content_merger中用预置话术替换
    #   优先级4: 全部正常 → 路由到content_merger
    graph.add_node("subgraph_output_router", subgraph_output_router)

    # 内容融合器: 读取agent_findings, 按优先级排序（投诉>售后>售中>售前>通用）,
    # fallback标记则用预置话术替代, 输出merged_content
    graph.add_node("content_merger", content_merger)

    # 语气与合规适配器: 根据emotion/customer_tier/strategy_version调整回复语气,
    # 输出draft_response
    graph.add_node("tone_adapter", tone_adapter)

    # 输出关卡（三级路由决策点）:
    #   安全检查(PII/有害内容) + LLM质量评分 → 确定risk_level
    #   低风险 → respond_to_customer（全自动发送）
    #   中风险 → tone_adapter（自动修正循环, 最多1次）
    #   高风险/critical → human_review 或 escalate_to_human
    graph.add_node("output_gate", output_gate)

    # 澄清发送节点（旁路, 绕过merger/adapter/gate）:
    #   仅做基本安全检查(PII过滤+有害内容), 直接发送追问给客户,
    #   设置pending_clarification=True等待客户回复后恢复到原子图
    graph.add_node("clarify_to_customer", clarify_to_customer)

    # 人工审核断点: interrupt()暂停执行, 等待5种人工决策:
    #   批准/编辑 → output_gate复查（安全闭环）
    #   拒绝-重生成 → content_merger（带人工反馈重新生成）
    #   拒绝-重分诊 → orchestrator_gate（轻量模式, 跳过安全审核仅重做意图分类）
    #   接管 → escalate_to_human + 设置session_takeover=True
    # 最多2轮防死循环, 超限强制转人工
    graph.add_node("human_review", human_review)

    # 【终端节点】
    # 发送最终回复给客户, 流程结束
    graph.add_node("respond_to_customer", respond_to_customer)
    # 转接人工客服, 流程结束
    graph.add_node("escalate_to_human", escalate_to_human)

    # ==================== 入口 ====================
    # 所有客户消息首先进入orchestrator_gate统一处理
    graph.set_entry_point("orchestrator_gate")

    # ==================== 条件边: orchestrator_gate路由 ====================
    # route_by_labels 根据active_agents决定路由目标:
    #   - active_agents含"escalate_to_human" → 直接escalate_to_human（转人工快捷通道）
    #   - escalate_signal=="to_human" → escalate_to_human（子图升级信号）
    #   - escalate_signal=="to_complaint" → complaint_agent（子图升级到投诉）
    #   - pending_clarification==True → 路由到pending_subgraph（澄清重入, 跳过全部分诊）
    #   - 正常: 按active_agents列表路由（支持多子图并行扇出, 如同时激活售前+通用）
    #   - 兜底: active_agents为空时路由到general_agent
    graph.add_conditional_edges(
        "orchestrator_gate",
        route_by_labels,
        {
            "presales_agent": "presales_agent",
            "insales_agent": "insales_agent",
            "aftersales_agent": "aftersales_agent",
            "complaint_agent": "complaint_agent",
            "general_agent": "general_agent",
            "escalate_to_human": "escalate_to_human",
        },
    )

    # ==================== 子图输出 → subgraph_output_router ====================
    # 所有子图完成后无条件汇入subgraph_output_router统一处理,
    # 由route_after_output_router按优先级决定下一步路由
    for agent in ["presales_agent", "insales_agent", "aftersales_agent",
                  "complaint_agent", "general_agent"]:
        graph.add_edge(agent, "subgraph_output_router")

    # ==================== subgraph_output_router → 条件路由 ====================
    # route_after_output_router 优先级路由逻辑:
    #   1. escalate_signal存在:
    #        "to_complaint" → complaint_agent（中断其他子图, 切到投诉）
    #        其他 → escalate_to_human
    #   2. clarification_request存在 且 clarification_attempts < 2:
    #        → clarify_to_customer（澄清旁路, 忽略其他子图正常结果）
    #   3. clarification_request存在 且 clarification_attempts >= 2:
    #        → escalate_to_human（澄清2次仍不足, 转人工）
    #   4. requires_human_review且无agent_findings:
    #        → escalate_to_human（澄清超限转人工的标记）
    #   5. 默认 → content_merger（正常流程或fallback已标记的情况）
    graph.add_conditional_edges(
        "subgraph_output_router",
        route_after_output_router,
        {
            "content_merger": "content_merger",
            "clarify_to_customer": "clarify_to_customer",
            "complaint_agent": "complaint_agent",
            "escalate_to_human": "escalate_to_human",
        },
    )

    # ==================== 主链路（无条件直连边）====================
    # content_merger → tone_adapter → output_gate: 线性输出管线
    #   content_merger: 融合子图结果为merged_content
    #   tone_adapter: 根据情感/客户等级调整语气, 输出draft_response
    #   output_gate: 安全+质量评估, 输出risk_level决定三级路由
    graph.add_edge("content_merger", "tone_adapter")
    graph.add_edge("tone_adapter", "output_gate")

    # ==================== output_gate → 三级路由 ====================
    # three_way_route 根据risk_level和quality_score路由:
    #   - risk_level=="critical" → escalate_to_human（关键风险, 直接转人工）
    #   - risk_level=="high" 或 quality_score < QUALITY_SCORE_CRITICAL
    #        → human_review（高风险, 人工审核断点）
    #   - risk_level=="medium" 且 auto_correction_attempts < 1
    #        → tone_adapter（中风险自动修正, 进入修正循环）
    #   - risk_level=="medium" 且 auto_correction_attempts >= 1
    #        → human_review（v4: 修正后仍不通过, 直接升级为高风险）
    #   - quality_score < QUALITY_SCORE_REPROCESS 且 resolution_attempts < max
    #        → orchestrator_gate（质量过低, 重新处理整个流程）
    #   - risk_level=="low" 且 quality_score达标
    #        → respond_to_customer（低风险, 全自动发送）
    graph.add_conditional_edges(
        "output_gate",
        three_way_route,
        {
            "respond_to_customer": "respond_to_customer",
            "tone_adapter": "tone_adapter",
            "human_review": "human_review",
            "escalate_to_human": "escalate_to_human",
            "orchestrator_gate": "orchestrator_gate",
        },
    )

    # ==================== 人工审核 → 条件路由 ====================
    # route_after_human_review 根据5种人工决策路由:
    #   - "takeover" → escalate_to_human（接管, 设置session_takeover=True）
    #   - "reject_regenerate" → content_merger（带人工反馈重新生成, 沿用子图结果）
    #   - "reject_reclassify" → orchestrator_gate（轻量模式: 跳过安全审核, 仅重做意图分类+子图调度）
    #   - "approve" / "edit" → output_gate（安全闭环: 人工输出必须复查）
    #     output_gate复查不通过 → 回到human_review（human_review_rounds++）
    #     human_review_rounds >= 2 → escalate_to_human（强制转人工, 防死循环）
    graph.add_conditional_edges(
        "human_review",
        route_after_human_review,
        {
            "output_gate": "output_gate",
            "content_merger": "content_merger",
            "orchestrator_gate": "orchestrator_gate",
            "escalate_to_human": "escalate_to_human",
        },
    )

    # ==================== 终止边 ====================
    # 以下节点执行后流程结束（到达END）
    graph.add_edge("respond_to_customer", END)      # 回复已发送给客户
    graph.add_edge("escalate_to_human", END)         # 已转接人工客服
    graph.add_edge("clarify_to_customer", END)       # 澄清追问已发送, 等待客户回复

    return graph


def compile_supervisor_graph():
    """编译监督者图，返回可执行的CompiledGraph

    使用MemorySaver作为检查点后端, 支持会话持久化和interrupt()断点恢复。
    生产环境应替换为DatabaseCheckpointer。
    """
    graph = build_supervisor_graph()
    checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer)
