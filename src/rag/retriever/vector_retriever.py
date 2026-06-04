"""
向量检索器

使用 Embedding + ChromaDB 实现语义检索。
"""

from src.rag.embedder.base import BaseEmbedder
from src.rag.store.base import BaseStore
from src.rag.config import rag_settings


class VectorRetriever:
    def __init__(self, embedder: BaseEmbedder, store: BaseStore):
        self.embedder = embedder
        self.store = store

    def retrieve(self, query: str, top_k: int | None = None) -> list[tuple]:
        top_k = top_k or rag_settings.top_k
        query_embedding = self.embedder.embed_query(query)
        results = self.store.search(query_embedding, top_k)
        return [
            (doc, score) for doc, score in results
            if score >= rag_settings.similarity_threshold
        ]
