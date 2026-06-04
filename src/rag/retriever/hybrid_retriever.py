"""
混合检索器：BM25 + 向量检索 + RRF 融合

支持可选的 Reranker 精排。
"""

import time
from collections import defaultdict
from src.rag.embedder.base import BaseEmbedder
from src.rag.store.base import BaseStore
from src.rag.retriever.bm25_retriever import BM25Retriever
from src.rag.loader.base import Document
from src.rag.config import rag_settings
from src.rag.utils.logger import get_logger

log = get_logger("hybrid_retriever")


class HybridRetriever:
    """混合检索：BM25 + 向量检索 + RRF 融合"""

    def __init__(self, embedder: BaseEmbedder, store: BaseStore, use_reranker: bool = False):
        self.embedder = embedder
        self.store = store
        self.bm25 = BM25Retriever()
        self.rrf_k = 60
        self.reranker = None
        if use_reranker:
            try:
                from src.rag.retriever.reranker import Reranker
                self.reranker = Reranker()
                log.info("Reranker 已启用 (bge-reranker-v2-m3)")
            except Exception as e:
                log.warning("Reranker 加载失败，跳过: %s", e)

    def build_bm25_index(self, documents: list[Document]):
        """从文档列表构建 BM25 索引（在索引阶段调用）"""
        t0 = time.time()
        self.bm25.build_index(documents)
        self.bm25.save_index()
        log.info("BM25 索引构建+保存完成: %d 文档, 耗时 %.1fs", len(documents), time.time() - t0)

    def ensure_bm25_ready(self):
        """确保 BM25 索引可用：优先从缓存加载，没有则从 store 构建"""
        if self.bm25.load_index():
            return
        log.info("BM25 缓存不存在，从向量库构建...")
        all_docs_with_emb = self.store.get_all_documents()
        all_docs = [doc for doc, _ in all_docs_with_emb]
        self.build_bm25_index(all_docs)

    def _rrf_fuse(self, *rankings: list[tuple[str, float]]) -> list[tuple[str, float]]:
        rrf_map = defaultdict(float)
        for ranked_list in rankings:
            for rank, (doc_id, _) in enumerate(ranked_list, start=1):
                rrf_map[doc_id] += 1.0 / (self.rrf_k + rank)
        return sorted(rrf_map.items(), key=lambda x: x[1], reverse=True)

    def retrieve(self, query: str, top_k: int | None = None) -> list[tuple[Document, float]]:
        top_k = top_k or rag_settings.top_k
        fetch_n = top_k * 4

        # 1. 向量检索
        t0 = time.time()
        query_embedding = self.embedder.embed_query(query)
        vector_results = self.store.search(query_embedding, top_k=fetch_n)
        log.info("向量检索: %d 条, 耗时 %.2fs", len(vector_results), time.time() - t0)
        vector_ranking = [
            (f"{doc.metadata['source']}_{doc.metadata.get('chunk_index', i)}", score)
            for i, (doc, score) in enumerate(vector_results)
        ]

        # 2. BM25 检索
        t1 = time.time()
        bm25_results = self.bm25.search(query, top_k=fetch_n)
        log.info("BM25 检索: %d 条, 耗时 %.2fs", len(bm25_results), time.time() - t1)
        bm25_ranking = [
            (f"{doc.metadata['source']}_{doc.metadata.get('chunk_index', i)}", score)
            for i, (doc, score) in enumerate(bm25_results)
        ]

        # 3. RRF 融合
        fused = self._rrf_fuse(vector_ranking, bm25_ranking)
        fused_ids = [doc_id for doc_id, _ in fused[:top_k]]
        log.info("RRF 融合后: %d 条候选", len(fused_ids))

        # 4. 取回完整文档
        id_to_doc = {}
        for i, (doc, score) in enumerate(vector_results):
            doc_id = f"{doc.metadata['source']}_{doc.metadata.get('chunk_index', i)}"
            id_to_doc[doc_id] = (doc, score)

        # 同时从 BM25 结果中补充
        for i, (doc, score) in enumerate(bm25_results):
            doc_id = f"{doc.metadata['source']}_{doc.metadata.get('chunk_index', i)}"
            if doc_id not in id_to_doc:
                id_to_doc[doc_id] = (doc, score)

        results = []
        for doc_id in fused_ids:
            if doc_id in id_to_doc:
                results.append(id_to_doc[doc_id])

        # 5. Reranker 精排（可选）
        if self.reranker and results:
            t2 = time.time()
            reranked = self.reranker.rerank(
                query,
                [doc for doc, _ in results],
                top_k=top_k,
            )
            results = reranked
            log.info("Reranker 精排: %d → %d 条, 耗时 %.2fs", len(fused_ids), len(results), time.time() - t2)

        # 6. 过滤低相似度
        before = len(results)
        results = [
            (doc, score) for doc, score in results
            if score >= rag_settings.similarity_threshold
        ]
        if before != len(results):
            log.info("相似度过滤: %d → %d (阈值=%.2f)", before, len(results), rag_settings.similarity_threshold)
        return results
