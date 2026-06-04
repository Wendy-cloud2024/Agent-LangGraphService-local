"""
子图上下文注入包装器

在 supervisor 调用子图前，通过 inject_subgraph_context() 注入相关历史。
子图通过 state["relevant_history"] 获取上下文，无需直接访问外部存储。

用法:
    graph.add_node("presales_agent",
        create_subgraph_node("presales_agent", compile_presales_subgraph()))
"""

import logging

from src.tools.context_injection import inject_subgraph_context
from src.utils.observability import TraceTimer, trace

logger = logging.getLogger(__name__)


def create_subgraph_node(subgraph_name: str, compiled_subgraph):
    """创建带上下文注入的子图节点

    参数:
        subgraph_name: 子图名称 (presales_agent / insales_agent / ...)
        compiled_subgraph: 编译后的子图
    """
    def node_fn(state: dict) -> dict:
        timer = TraceTimer()
        timer.start()
        trace_id = state.get("trace_id", "")

        # 1. 注入上下文
        try:
            context = inject_subgraph_context(state, subgraph_name)
            relevant_history = context.get("relevant_history", [])
            logger.info(f"[{trace_id}] 上下文注入到 {subgraph_name}: {len(relevant_history)} 条")
        except Exception as e:
            logger.error(f"上下文注入失败 ({subgraph_name}): {e}")
            relevant_history = []

        # 2. 合并到 state (不修改原始 state, 构建 enriched 副本)
        enriched_state = dict(state)
        enriched_state["relevant_history"] = relevant_history

        # 3. 执行子图
        result = compiled_subgraph.invoke(enriched_state)

        # 4. 添加 trace
        if result is None:
            result = {}
        result.setdefault("trace_events", [
            trace(trace_id, subgraph_name, "completed", timer.elapsed_ms(),
                  {"context_injected": len(relevant_history)})
        ])

        return result

    # 保留子图名称方便调试
    node_fn.__name__ = subgraph_name
    return node_fn
