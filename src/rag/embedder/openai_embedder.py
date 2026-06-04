"""
OpenAI 兼容接口的 Embedding 实现

使用智谱 API（兼容 OpenAI 格式）生成向量。
内建速率限制：每批之间暂停，避免触发 429。
"""

import time
import logging
from openai import OpenAI
from .base import BaseEmbedder
from src.rag.config import rag_settings

logger = logging.getLogger("rag.openai_embedder")


class OpenAIEmbedder(BaseEmbedder):
    def __init__(self):
        kwargs = {"api_key": rag_settings.zhipu_api_key}
        if rag_settings.zhipu_base_url:
            kwargs["base_url"] = rag_settings.zhipu_base_url
        self.client = OpenAI(**kwargs)
        self.model = rag_settings.embedding_model

    def embed(self, texts: list[str], _retries: int = 0) -> list[list[float]]:
        try:
            response = self.client.embeddings.create(
                input=texts, model=self.model
            )
            return [item.embedding for item in response.data]
        except Exception as e:
            if _retries < 3 and "429" in str(e):
                wait = 2 ** (_retries + 1)
                logger.warning("Embedding 速率限制, 等待 %ds 后重试...", wait)
                time.sleep(wait)
                return self.embed(texts, _retries=_retries + 1)
            raise

    def embed_batch(self, texts: list[str], batch_size: int = 5) -> list[list[float]]:
        """分批 Embedding，避免速率限制"""
        all_embeddings = []
        total = len(texts)
        for i in range(0, total, batch_size):
            batch = texts[i:i + batch_size]
            logger.info("Embedding 批次 %d/%d (%d 条)", i // batch_size + 1, (total + batch_size - 1) // batch_size, len(batch))
            embeddings = self.embed(batch)
            all_embeddings.extend(embeddings)
            if i + batch_size < total:
                time.sleep(1.0)
        return all_embeddings

    def embed_query(self, text: str) -> list[float]:
        return self.embed([text])[0]
