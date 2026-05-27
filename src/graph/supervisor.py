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
    # 入口关卡
    graph.add_node("orchestrator_gate", orchestrator_gate)

    # 子图节点
    from src.graph.subgraphs.presales.graph import compile_presales_subgraph
    from src.graph.subgraphs.insales.graph import compile_insales_subgraph
    from src.graph.subgraphs.aftersales.graph import compile_aftersales_subgraph
    from src.graph.subgraphs.complaint.graph import compile_complaint_subgraph
    from src.graph.subgraphs.general.graph import compile_general_subgraph

    graph.add_node("presales_agent", compile_presales_subgraph())
    graph.add_node("insales_agent", compile_insales_subgraph())
    graph.add_node("aftersales_agent", compile_aftersales_subgraph())
    graph.add_node("complaint_agent", compile_complaint_subgraph())
    graph.add_node("general_agent", compile_general_subgraph())

    # 中间处理节点
    graph.add_node("subgraph_output_router", subgraph_output_router)
    graph.add_node("content_merger", content_merger)
    graph.add_node("tone_adapter", tone_adapter)
    graph.add_node("output_gate", output_gate)
    graph.add_node("clarify_to_customer", clarify_to_customer)
    graph.add_node("human_review", human_review)

    # 终端节点
    graph.add_node("respond_to_customer", respond_to_customer)
    graph.add_node("escalate_to_human", escalate_to_human)

    # ==================== 入口 ====================
    graph.set_entry_point("orchestrator_gate")

    # ==================== 条件边: orchestrator_gate路由 ====================
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
    for agent in ["presales_agent", "insales_agent", "aftersales_agent",
                  "complaint_agent", "general_agent"]:
        graph.add_edge(agent, "subgraph_output_router")

    # ==================== subgraph_output_router → 条件路由 ====================
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

    # ==================== 主链路 ====================
    graph.add_edge("content_merger", "tone_adapter")
    graph.add_edge("tone_adapter", "output_gate")

    # ==================== output_gate → 三级路由 ====================
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
    graph.add_edge("respond_to_customer", END)
    graph.add_edge("escalate_to_human", END)
    graph.add_edge("clarify_to_customer", END)

    return graph


def compile_supervisor_graph():
    """编译监督者图，返回可执行的CompiledGraph"""
    graph = build_supervisor_graph()
    checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer)
