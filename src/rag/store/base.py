"""
向量存储抽象基类
"""

from abc import ABC, abstractmethod
from src.rag.loader.base import Document


class BaseStore(ABC):
    @abstractmethod
    def add(self, documents: list[Document], embeddings: list[list[float]]) -> None:
        ...

    @abstractmethod
    def search(self, query_embedding: list[float], top_k: int = 5) -> list[tuple[Document, float]]:
        """返回 [(Document, similarity_score), ...]"""
        ...

    @abstractmethod
    def delete(self, source: str) -> None:
        """删除指定来源的所有向量"""
        ...
