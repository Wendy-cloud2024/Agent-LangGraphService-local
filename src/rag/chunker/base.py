"""
分块器基类
"""

from abc import ABC, abstractmethod
from src.rag.loader.base import Document


class BaseChunker(ABC):
    @abstractmethod
    def split(self, document: Document) -> list[Document]:
        ...
