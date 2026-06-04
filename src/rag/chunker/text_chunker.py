"""
递归文本分块器

按分隔符层级递归切分，保持语义完整性。
"""

from src.rag.loader.base import Document
from .base import BaseChunker


class TextChunker(BaseChunker):
    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 64):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = ["\n\n", "\n", "。", ".", " ", ""]

    def split(self, document: Document) -> list[Document]:
        text = document.content
        if len(text) <= self.chunk_size:
            return [document]

        chunks = self._recursive_split(text, self.separators)
        return [
            Document(content=chunk, metadata={
                **document.metadata,
                "chunk_index": i,
                "chunk_total": len(chunks),
            })
            for i, chunk in enumerate(chunks)
        ]

    def _recursive_split(self, text: str, separators: list[str]) -> list[str]:
        if not text:
            return []
        if len(text) <= self.chunk_size:
            return [text]
        if not separators:
            return [text[i:i + self.chunk_size]
                    for i in range(0, len(text), self.chunk_size - self.chunk_overlap)]

        sep = separators[0]
        parts = text.split(sep)
        result, current = [], ""

        for part in parts:
            candidate = current + sep + part if current else part
            if len(candidate) <= self.chunk_size:
                current = candidate
            else:
                if current:
                    result.append(current)
                if len(part) > self.chunk_size:
                    result.extend(self._recursive_split(part, separators[1:]))
                    current = ""
                else:
                    current = part
        if current:
            result.append(current)
        return result
