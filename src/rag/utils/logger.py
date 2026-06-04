"""
RAG 模块日志工具

融入 thesis-agent 的 logging 体系，使用标准 logging.getLogger。
"""

import logging


def get_logger(name: str) -> logging.Logger:
    """获取 RAG 模块的子 logger"""
    return logging.getLogger(f"rag.{name}")
