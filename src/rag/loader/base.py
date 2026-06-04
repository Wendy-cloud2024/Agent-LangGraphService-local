"""
文档加载器基类

Document 数据类和 BaseLoader 抽象基类。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Document:
    content: str
    metadata: dict  # {"source": 路径, "type": 文件类型, "filename": 文件名}


class BaseLoader(ABC):
    @abstractmethod
    def load(self, source: str | Path) -> list[Document]:
        ...
