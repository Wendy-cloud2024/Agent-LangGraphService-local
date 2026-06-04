"""
RAG 模块入口

提供 get_rag_retriever() 懒加载单例，供子图工具函数调用。
首次调用时初始化 ChromaDB + BM25 + 混合检索器。
"""

import logging
from src.rag.retriever.hybrid_retriever import HybridRetriever

logger = logging.getLogger("rag")

_retriever: HybridRetriever | None = None


def get_rag_retriever() -> HybridRetriever:
    """获取 RAG 检索器单例

    首次调用时初始化:
    1. OpenAIEmbedder（智谱 embedding-3）
    2. ChromaStore（ChromaDB 持久化存储）
    3. HybridRetriever（向量 + BM25 + RRF 融合）
    4. 确保 BM25 索引就绪

    后续调用直接返回缓存实例。
    """
    global _retriever
    if _retriever is not None:
        return _retriever

    logger.info("初始化 RAG 检索器...")

    from src.rag.embedder.openai_embedder import OpenAIEmbedder
    from src.rag.store.chroma_store import ChromaStore

    embedder = OpenAIEmbedder()
    store = ChromaStore()
    _retriever = HybridRetriever(embedder, store, use_reranker=False)
    _retriever.ensure_bm25_ready()

    logger.info("RAG 检索器初始化完成")
    return _retriever
