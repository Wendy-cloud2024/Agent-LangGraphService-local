"""
ChromaDB 持久化向量存储

使用 cosine 相似度，向量数据持久化到 .chroma_db/ 目录。
"""

import chromadb
from src.rag.loader.base import Document
from .base import BaseStore
from src.rag.config import rag_settings
from src.rag.utils.logger import get_logger

log = get_logger("chroma_store")


class ChromaStore(BaseStore):
    def __init__(self):
        self.client = chromadb.PersistentClient(
            path=str(rag_settings.resolved_vector_db_dir)
        )
        self.collection = self.client.get_or_create_collection(
            name="ecommerce_knowledge",
            metadata={"hnsw:space": "cosine"}
        )
        log.info("ChromaDB 初始化, 集合现有 %d 条记录", self.collection.count())

    def add(self, documents: list[Document], embeddings: list[list[float]]) -> None:
        if not documents:
            return
        ids = [f"{doc.metadata['source']}_{doc.metadata.get('chunk_index', i)}"
               for i, doc in enumerate(documents)]
        metadatas = [{k: str(v) for k, v in doc.metadata.items()} for doc in documents]
        self.collection.upsert(
            ids=ids,
            documents=[doc.content for doc in documents],
            embeddings=embeddings,
            metadatas=metadatas,
        )
        log.debug("写入 %d 条向量", len(documents))

    def search(self, query_embedding: list[float], top_k: int = 5) -> list[tuple[Document, float]]:
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
        )
        docs_with_scores = []
        if not results["documents"] or not results["documents"][0]:
            return docs_with_scores
        for i, doc_content in enumerate(results["documents"][0]):
            metadata = results["metadatas"][0][i]
            score = 1 - results["distances"][0][i]
            docs_with_scores.append((
                Document(content=doc_content, metadata=metadata),
                score
            ))
        log.debug("向量检索返回 %d 条 (top_k=%d)", len(docs_with_scores), top_k)
        return docs_with_scores

    def delete(self, source: str) -> None:
        try:
            self.collection.delete(where={"source": source})
            log.info("已删除来源: %s", source)
        except Exception:
            pass

    def get_all_documents(self) -> list[tuple[Document, list[float]]]:
        results = self.collection.get(include=["documents", "metadatas", "embeddings"])
        docs_with_embeddings = []
        for i, content in enumerate(results["documents"]):
            metadata = results["metadatas"][i]
            embedding = results["embeddings"][i]
            docs_with_embeddings.append((
                Document(content=content, metadata=metadata),
                embedding
            ))
        log.info("加载全部 %d 条文档", len(docs_with_embeddings))
        return docs_with_embeddings
