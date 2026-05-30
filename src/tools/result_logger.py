"""
Invoke结果日志工具

功能:
- 将invoke返回的状态解析为JSON并记录日志
- 从LangSmith拉取本次执行的节点路径，在终端打印经过的点位
"""

import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def _serialize_value(v):
    """将不可JSON序列化的值转为可序列化形式"""
    if hasattr(v, "to_json"):
        return v.to_json()
    if hasattr(v, "model_dump"):
        return v.model_dump(mode="json")
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, bytes):
        return f"<bytes len={len(v)}>"
    return str(v)


def log_invoke_result(result: dict):
    """将invoke返回的状态解析为JSON并记录日志"""
    try:
        serializable = {}
        for k, v in result.items():
            try:
                json.dumps({k: v}, default=_serialize_value, ensure_ascii=False)
                serializable[k] = v
            except (TypeError, ValueError):
                serializable[k] = _serialize_value(v)

        log_data = json.dumps(serializable, default=_serialize_value, ensure_ascii=False, indent=2)
        logger.info("Invoke结果:\n%s", log_data)
    except Exception as e:
        logger.warning("序列化invoke结果失败: %s", e)


def _fetch_run_tree(client, run_id, depth=0, max_depth=5):
    """递归获取LangSmith run的执行树"""
    tree = {"name": str(run_id.name), "type": run_id.run_type, "children": []}
    if depth >= max_depth:
        return tree
    try:
        children = list(client.list_runs(run_id=run_id.id, limit=50))
        for child in children:
            tree["children"].append(_fetch_run_tree(client, child, depth + 1, max_depth))
    except Exception:
        pass
    return tree


def _format_tree(node, depth=0):
    """格式化执行树为缩进文本"""
    prefix = "  " * depth
    connector = "|-- " if depth > 0 else ""
    line = f"{prefix}{connector}{node['name']} ({node['type']})"
    lines = [line]
    for child in node["children"]:
        lines.extend(_format_tree(child, depth + 1))
    return lines


def log_execution_path(result: dict):
    """从LangSmith拉取最近一次trace，打印本次invoke经过的节点路径"""
    try:
        from langsmith import Client
        import os

        if os.getenv("LANGCHAIN_TRACING_V2") != "true":
            return

        client = Client()
        project = os.getenv("LANGCHAIN_PROJECT", "thesis-agent")
        trace_id = result.get("trace_id", "")

        # 找到最近一次图执行的根run（run_type=chain）
        runs = list(client.list_runs(
            project_name=project,
            run_type="chain",
            limit=5,
        ))

        if not runs:
            return

        # 匹配本次trace_id: 检查root run的metadata或子run
        target_run = None
        for run in runs:
            # 优先找包含当前trace_id的run
            try:
                children = list(client.list_runs(run_id=run.id, limit=50))
                for child in children:
                    if hasattr(child, "extra") and child.extra:
                        metadata = child.extra.get("metadata", {})
                        if trace_id and trace_id in str(metadata):
                            target_run = run
                            break
            except Exception:
                pass
            if target_run:
                break

        # 如果没匹配到trace_id，取最近一次
        if not target_run:
            target_run = runs[0]

        # 构建执行树并打印
        tree = _fetch_run_tree(client, target_run)
        lines = _format_tree(tree)
        path_text = "\n".join(lines)

        print("\n[执行路径]")
        print(path_text)
        print(f"[trace_id] {trace_id}")
        print(f"[LangSmith] https://smith.langchain.com/o/default/projects/p/{project}\n")

    except Exception as e:
        logger.warning("获取执行路径失败: %s", e)
