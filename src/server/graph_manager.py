"""图管理器 — 桥接 FastAPI 与 LangGraph

封装图编译单例、对话调用、中断检测/恢复，复用 main.py 和 human_sim/simulator.py 的模式。
"""

import logging
import threading
from typing import Any

from langchain_core.messages import HumanMessage
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from src.graph.supervisor import compile_supervisor_graph
from src.state.schema import create_initial_state
from src.utils.observability import generate_trace_id
from src.graph.nodes.escalate_to_human import release_takeover

logger = logging.getLogger(__name__)


class GraphManager:
    """线程安全的图管理器，持有编译后的图单例"""

    def __init__(self):
        self._graph: CompiledStateGraph | None = None
        self._lock = threading.Lock()

    def get_graph(self) -> CompiledStateGraph:
        """获取编译后的图单例（首次调用时编译）"""
        if self._graph is None:
            with self._lock:
                if self._graph is None:
                    logger.info("正在编译 supervisor 图...")
                    self._graph = compile_supervisor_graph()
                    logger.info("supervisor 图编译完成")
        return self._graph

    def invoke_turn(
        self,
        thread_id: str,
        customer_id: str,
        customer_tier: str,
        message: str,
        is_first_turn: bool,
    ) -> list[dict[str, Any]]:
        """同步执行一轮对话，返回事件列表。

        事件类型:
          - node_progress: 节点执行进度
          - human_review_request: 人工审核中断
          - approval_request: 投诉审批中断
          - chat_response: 最终回复（含元数据）
          - error: 错误
        """
        graph = self.get_graph()
        config = {"configurable": {"thread_id": thread_id}}
        trace_id = generate_trace_id()

        try:
            # === 构建输入状态 ===
            if is_first_turn:
                from src.memory.customer_store import get_customer_store
                store = get_customer_store()
                profile = store.load(customer_id)
                input_state: dict = create_initial_state(
                    session_id=thread_id,
                    customer_id=customer_id,
                    customer_tier=customer_tier,
                )
                input_state["customer_profile"] = profile
                input_state["messages"] = [HumanMessage(content=message)]
            else:
                input_state = {
                    "messages": [HumanMessage(content=message)],
                }
            input_state["trace_id"] = trace_id

            # === 流式收集节点进度 ===
            events: list[dict[str, Any]] = []
            for event in graph.stream(input_state, config, stream_mode="updates"):
                for node_name, node_output in event.items():
                    if node_name == "__end__":
                        continue
                    tags: dict[str, Any] = {}
                    for key in ("risk_level", "quality_score", "resolution_status",
                                "emotion", "urgency", "routing_reason"):
                        val = node_output.get(key)
                        if val is not None and val != "" and val != 0.0:
                            tags[key] = val
                    events.append({
                        "type": "node_progress",
                        "node": node_name,
                        "tags": tags,
                    })

            # === 检查中断 ===
            snapshot = graph.get_state(config)
            for task in snapshot.tasks:
                if task.interrupts:
                    interrupt_value = task.interrupts[0].value
                    if isinstance(interrupt_value, dict):
                        if "draft_response" in interrupt_value or "risk_level" in interrupt_value:
                            events.append({
                                "type": "human_review_request",
                                "review_info": interrupt_value,
                            })
                        elif "plan" in interrupt_value or "severity" in interrupt_value:
                            events.append({
                                "type": "approval_request",
                                "approval_info": interrupt_value,
                            })
                        else:
                            events.append({
                                "type": "human_review_request",
                                "review_info": interrupt_value,
                            })
                    return events

            # === 提取最终结果 ===
            values = snapshot.values
            content = values.get("draft_response", "") or values.get("merged_content", "")
            metadata = {
                "intent_labels": values.get("intent_labels", []),
                "emotion": values.get("emotion", ""),
                "emotion_intensity": values.get("emotion_intensity", 0.0),
                "urgency": values.get("urgency", ""),
                "routing_reason": values.get("routing_reason", ""),
                "active_agents": values.get("active_agents", []),
                "risk_level": values.get("risk_level", ""),
                "quality_score": values.get("quality_score", 0.0),
                "resolution_status": values.get("resolution_status", ""),
                "session_takeover": values.get("session_takeover", False),
            }
            events.append({
                "type": "chat_response",
                "content": content or "抱歉，我暂时无法处理您的请求。",
                "metadata": metadata,
            })
            return events

        except Exception as e:
            logger.error(f"对话执行失败: {e}", exc_info=True)
            return [{"type": "error", "message": f"对话执行失败: {e}"}]

    def resume_interrupt(
        self,
        thread_id: str,
        resume_value: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """恢复中断，返回后续事件列表。"""
        graph = self.get_graph()
        config = {"configurable": {"thread_id": thread_id}}

        try:
            events: list[dict[str, Any]] = []

            # 流式执行恢复后的节点
            for event in graph.stream(Command(resume=resume_value), config, stream_mode="updates"):
                for node_name, node_output in event.items():
                    if node_name == "__end__":
                        continue
                    tags: dict[str, Any] = {}
                    for key in ("risk_level", "quality_score", "resolution_status",
                                "emotion", "urgency", "routing_reason"):
                        val = node_output.get(key)
                        if val is not None and val != "" and val != 0.0:
                            tags[key] = val
                    events.append({
                        "type": "node_progress",
                        "node": node_name,
                        "tags": tags,
                    })

            # 再次检查是否还有中断（人工审核最多2轮）
            snapshot = graph.get_state(config)
            for task in snapshot.tasks:
                if task.interrupts:
                    interrupt_value = task.interrupts[0].value
                    if isinstance(interrupt_value, dict):
                        if "draft_response" in interrupt_value or "risk_level" in interrupt_value:
                            events.append({
                                "type": "human_review_request",
                                "review_info": interrupt_value,
                            })
                        elif "plan" in interrupt_value or "severity" in interrupt_value:
                            events.append({
                                "type": "approval_request",
                                "approval_info": interrupt_value,
                            })
                    return events

            # 提取最终结果
            values = snapshot.values
            content = values.get("draft_response", "") or values.get("merged_content", "")
            metadata = {
                "intent_labels": values.get("intent_labels", []),
                "emotion": values.get("emotion", ""),
                "emotion_intensity": values.get("emotion_intensity", 0.0),
                "urgency": values.get("urgency", ""),
                "routing_reason": values.get("routing_reason", ""),
                "active_agents": values.get("active_agents", []),
                "risk_level": values.get("risk_level", ""),
                "quality_score": values.get("quality_score", 0.0),
                "resolution_status": values.get("resolution_status", ""),
                "session_takeover": values.get("session_takeover", False),
            }
            events.append({
                "type": "chat_response",
                "content": content or "抱歉，我暂时无法处理您的请求。",
                "metadata": metadata,
            })
            return events

        except Exception as e:
            logger.error(f"恢复中断失败: {e}", exc_info=True)
            return [{"type": "error", "message": f"恢复中断失败: {e}"}]

    def get_session_state(self, thread_id: str) -> dict[str, Any]:
        """获取会话状态快照"""
        graph = self.get_graph()
        config = {"configurable": {"thread_id": thread_id}}
        snapshot = graph.get_state(config)
        values = snapshot.values
        return {
            "takeover": values.get("session_takeover", False),
            "resolution_status": values.get("resolution_status", ""),
            "message_count": len(values.get("messages", [])),
            "pending_nodes": list(snapshot.next) if snapshot.next else [],
        }

    def do_release_takeover(self, thread_id: str) -> dict[str, Any]:
        """释放接管模式"""
        graph = self.get_graph()
        config = {"configurable": {"thread_id": thread_id}}
        try:
            result = release_takeover(graph, config)
            if result is not None:
                return {"type": "status_response", "takeover": False,
                        "resolution_status": result.get("resolution_status", "")}
            else:
                return {"type": "error", "message": "释放接管失败"}
        except Exception as e:
            return {"type": "error", "message": f"释放接管失败: {e}"}


# 全局单例
graph_manager = GraphManager()
