"""
索引流水线

支持全量索引和增量索引：
- 全量：清空后重新索引 data/knowledge/ 下所有文档
- 增量：通过文件哈希检测变更，只处理新增/修改的文件
"""

import time
from src.rag.loader.directory_loader import DirectoryLoader
from src.rag.chunker.text_chunker import TextChunker
from src.rag.embedder.base import BaseEmbedder
from src.rag.store.base import BaseStore
from src.rag.utils.hash_tracker import HashTracker
from src.rag.retriever.bm25_retriever import BM25Retriever
from src.rag.utils.logger import get_logger

log = get_logger("index_pipeline")


class IndexPipeline:

    def __init__(self, embedder: BaseEmbedder, store: BaseStore):
        self.loader = DirectoryLoader()
        self.text_chunker = TextChunker()
        self.embedder = embedder
        self.store = store
        self.hash_tracker = HashTracker()
        self.bm25 = BM25Retriever()

    def _load_and_split(self, source_path: str) -> tuple:
        documents = self.loader.load(source_path)
        chunks = []
        for doc in documents:
            chunks.extend(self.text_chunker.split(doc))
        log.info("加载 %d 个文件 → %d 个块", len(documents), len(chunks))
        return documents, chunks

    def _embed_and_store(self, chunks: list):
        if not chunks:
            return
        batch_size = 30
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            texts = [c.content for c in batch]
            # 使用 embed_batch 分批调用，内置速率限制保护
            embeddings = self.embedder.embed_batch(texts, batch_size=5)
            self.store.add(batch, embeddings)
            log.info("索引进度 %d/%d", min(i + batch_size, len(chunks)), len(chunks))

    def run(self, source_path: str, incremental: bool = False) -> dict:
        """执行索引

        参数:
            source_path: 知识库数据目录路径
            incremental: 是否增量索引
        """
        from pathlib import Path
        root = Path(source_path)
        current_files = {str(p) for p in root.rglob("*") if p.is_file()}

        if not incremental:
            log.info("开始全量索引: %s", source_path)
            t0 = time.time()
            documents, chunks = self._load_and_split(source_path)
            self._embed_and_store(chunks)
            self.bm25.build_index(chunks)
            self.bm25.save_index()
            changes = self.hash_tracker.detect_changes(current_files)
            self.hash_tracker.save(changes["new_db"])
            elapsed = time.time() - t0
            log.info("全量索引完成: %d 文件, %d 块, 耗时 %.1fs", len(documents), len(chunks), elapsed)
            return {"files": len(documents), "chunks": len(chunks)}

        # 增量索引
        log.info("开始增量索引: %s", source_path)
        t0 = time.time()
        changes = self.hash_tracker.detect_changes(current_files)
        added = changes["added"]
        modified = changes["modified"]
        deleted = changes["deleted"]
        to_index = added + modified

        log.info("增量检测: 新增 %d, 修改 %d, 删除 %d", len(added), len(modified), len(deleted))

        for f in deleted + modified:
            self.store.delete(f)

        total_chunks = 0
        for filepath in to_index:
            _, chunks = self._load_and_split(filepath)
            self._embed_and_store(chunks)
            total_chunks += len(chunks)

        self.hash_tracker.save(changes["new_db"])
        # 增量索引后重建 BM25
        all_docs_with_emb = self.store.get_all_documents()
        all_docs = [doc for doc, _ in all_docs_with_emb]
        self.bm25.build_index(all_docs)
        self.bm25.save_index()
        elapsed = time.time() - t0
        log.info("增量索引完成: %d 文件, %d 块, 耗时 %.1fs", len(to_index), total_chunks, elapsed)
        return {"files": len(to_index), "chunks": total_chunks}
