"""
纯文本 / Markdown 文档加载器
"""

from pathlib import Path
from .base import BaseLoader, Document


class DocLoader(BaseLoader):
    def load(self, source: str | Path) -> list[Document]:
        path = Path(source)
        return [Document(
            content=path.read_text(encoding="utf-8"),
            metadata={
                "source": str(path),
                "type": "document",
                "filename": path.name,
            }
        )]
