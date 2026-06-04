"""
RAG 模块配置

从 .env 加载 RAG 相关配置，使用 RAG_ 前缀。
向量库和数据目录指向 thesis-agent 项目内的路径。
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

# 加载 .env
load_dotenv()


class RAGSettings(BaseSettings):
    # 路径配置 — 指向 thesis-agent 项目根目录
    project_root: Path = Path(__file__).resolve().parent.parent.parent
    data_dir: Path = Path("data/knowledge")
    vector_db_dir: Path = Path(".chroma_db")

    @property
    def resolved_data_dir(self) -> Path:
        p = self.data_dir
        return p if p.is_absolute() else (self.project_root / p).resolve()

    @property
    def resolved_vector_db_dir(self) -> Path:
        p = self.vector_db_dir
        return p if p.is_absolute() else (self.project_root / p).resolve()

    # Embedding 配置（阿里云 DashScope）
    embedding_provider: str = "aliyun"
    embedding_model: str = "text-embedding-v4"
    embedding_dimension: int = 1024

    # 阿里云 DashScope API（Embedding 使用）
    zhipu_api_key: str = os.getenv("RAG_ZHIPU_API_KEY", "")
    zhipu_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    # 分块配置
    chunk_size: int = 512
    chunk_overlap: int = 64

    # 检索配置
    top_k: int = 5
    similarity_threshold: float = 0.3

    # BM25 缓存路径
    bm25_cache_path: Path = Path("index/bm25_cache.pkl")

    model_config = {"env_prefix": "RAG_", "env_file": ".env", "extra": "ignore"}


rag_settings = RAGSettings()
