"""
全链路观测工具

每个主要节点调用 trace() 写入观测事件:
  trace(trace_id, node, status, duration_ms, metadata)

关键度量指标:
- 平均处理时长
- 分诊准确率
- 人工升级率
- 自动修正成功率
- 子图调用成功率
- 澄清回路触发率
- Fallback降级率
- 客户满意度(CSAT)
"""

import time
import uuid
import functools
from typing import Any

from src.config.settings import TRACE_ENABLED, TRACE_SAMPLE_RATE


def generate_trace_id() -> str:
    """生成追踪ID"""
    return str(uuid.uuid4())


def trace(
    trace_id: str,
    node: str,
    status: str = "started",
    duration_ms: float = 0.0,
    metadata: dict[str, Any] | None = None,
) -> dict:
    """记录一条观测事件

    参数:
        trace_id: 追踪ID
        node: 节点名称
        status: started/completed/failed
        duration_ms: 执行耗时(毫秒)
        metadata: 额外元数据

    返回: 事件字典，可直接追加到state["trace_events"]
    """
    event = {
        "trace_id": trace_id,
        "node": node,
        "status": status,
        "duration_ms": duration_ms,
        "metadata": metadata or {},
        "timestamp": time.time(),
    }
    if TRACE_ENABLED:
        return event
    return {}


class TraceTimer:
    """简单的计时器，用于测量节点执行耗时"""

    def __init__(self):
        self._start = 0.0

    def start(self):
        self._start = time.perf_counter()

    def elapsed_ms(self) -> float:
        return (time.perf_counter() - self._start) * 1000


def traced(node_name: str):
    """装饰器: 自动为节点函数添加计时和 trace 事件

    用法:
        @traced("my_node")
        def my_node(state: dict) -> dict:
            # 不需要手动创建 timer/trace_id
            result = do_something()
            return {"key": value}

    被装饰的函数返回的 dict 中会自动注入 trace_events。
    如果函数自身已设置了 trace_events，则不会覆盖。
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(state: dict) -> dict:
            timer = TraceTimer()
            timer.start()
            trace_id = state.get("trace_id", "")
            result = func(state)
            result.setdefault("trace_events", [
                trace(trace_id, node_name, "completed", timer.elapsed_ms())
            ])
            return result
        return wrapper
    return decorator
