"""
目录递归加载器

自动识别文件类型并分派到对应的 Loader。
"""

from pathlib import Path
from .base import BaseLoader, Document
from .doc_loader import DocLoader
from .docx_loader import DocxLoader


class DirectoryLoader(BaseLoader):
    SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".idea", ".chroma_db"}

    def __init__(self):
        self.doc_loader = DocLoader()
        self.docx_loader = DocxLoader()
        self.doc_extensions = {".md", ".txt", ".rst", ".json", ".yaml", ".yml", ".toml"}
        self.docx_extensions = {".docx"}

    def load(self, source: str | Path) -> list[Document]:
        root = Path(source)
        documents = []
        for path in root.rglob("*"):
            if any(skip in path.parts for skip in self.SKIP_DIRS):
                continue
            if not path.is_file():
                continue
            try:
                if path.suffix in self.docx_extensions:
                    documents.extend(self.docx_loader.load(path))
                elif path.suffix in self.doc_extensions:
                    documents.extend(self.doc_loader.load(path))
            except (UnicodeDecodeError, PermissionError):
                continue
        return documents
