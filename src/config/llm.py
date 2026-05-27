"""
LLM工厂函数 - 统一创建ChatOpenAI实例，自动注入base_url
"""

import os
from langchain_openai import ChatOpenAI


def create_llm(model: str, temperature: float = 0, **kwargs) -> ChatOpenAI:
    """创建LLM实例，自动注入DeepSeek API的base_url"""
    base_url = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
    return ChatOpenAI(
        model=model,
        temperature=temperature,
        base_url=base_url,
        **kwargs,
    )
