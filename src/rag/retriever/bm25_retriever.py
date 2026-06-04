"""
BM25 关键词检索器

使用 jieba 分词 + rank_bm25 实现中文关键词检索。
索引缓存到磁盘，避免每次重建。
"""

import pickle
from pathlib import Path

import jieba
from rank_bm25 import BM25Okapi
from src.rag.loader.base import Document
from src.rag.utils.logger import get_logger
from src.rag.config import rag_settings

log = get_logger("bm25_retriever")


class BM25Retriever:
    """基于 BM25 的关键词检索器"""

    def __init__(self):
        self.bm25 = None
        self.documents: list[Document] = []
        self.tokenized_corpus: list[list[str]] = []

    def build_index(self, documents: list[Document]):
        """构建 BM25 索引"""
        self.documents = documents
        self.tokenized_corpus = [self._tokenize(doc.content) for doc in documents]
        self.bm25 = BM25Okapi(self.tokenized_corpus)

    def save_index(self, path: str | Path | None = None):
        """持久化 BM25 索引到磁盘"""
        path = Path(path) if path else rag_settings.project_root / rag_settings.bm25_cache_path
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "documents": [(doc.content, doc.metadata) for doc in self.documents],
            "tokenized_corpus": self.tokenized_corpus,
            "bm25": self.bm25,
        }
        with open(path, "wb") as f:
            pickle.dump(data, f)
        log.info("BM25 索引已保存: %s (%d 条)", path, len(self.documents))

    def load_index(self, path: str | Path | None = None) -> bool:
        """从磁盘加载 BM25 索引，成功返回 True"""
        path = Path(path) if path else rag_settings.project_root / rag_settings.bm25_cache_path
        if not path.exists():
            return False
        with open(path, "rb") as f:
            data = pickle.load(f)
        self.documents = [
            Document(content=content, metadata=meta)
            for content, meta in data["documents"]
        ]
        self.tokenized_corpus = data["tokenized_corpus"]
        self.bm25 = data["bm25"]
        log.info("BM25 索引已加载: %s (%d 条)", path, len(self.documents))
        return True

    def _tokenize(self, text: str) -> list[str]:
        return list(jieba.cut(text))

    def search(self, query: str, top_k: int = 20) -> list[tuple[Document, float]]:
        if self.bm25 is None:
            return []
        tokenized_query = self._tokenize(query)
        scores = self.bm25.get_scores(tokenized_query)
        ranked_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        return [(self.documents[i], float(scores[i])) for i in ranked_indices if scores[i] > 0]
