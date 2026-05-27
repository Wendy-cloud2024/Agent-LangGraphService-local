"""
公共 JSON 解析工具

从 LLM 响应中提取 JSON，处理 Markdown 代码块包裹和花括号转义。
"""

import re
import json
import logging

logger = logging.getLogger(__name__)


def parse_json_response(content: str) -> dict:
    """从 LLM 响应中提取 JSON

    支持:
    - ```json ... ``` 代码块
    - ``` ... ``` 代码块
    - 裸 JSON 对象
    - {{ }} 转义花括号

    返回: 解析后的字典，失败返回空字典
    """
    # 尝试提取 ```json ... ``` 代码块
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", content)
    if match:
        content = match.group(1).strip()
    else:
        # 尝试提取第一个 { ... } 块
        match = re.search(r"\{[\s\S]*\}", content)
        if match:
            content = match.group(0)
    # 处理转义花括号
    content = content.replace("{{", "{").replace("}}", "}")
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        logger.warning(f"JSON解析失败: {content[:200]}")
        return {}
