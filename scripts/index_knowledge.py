"""
电商知识库索引脚本

用法:
  python scripts/index_knowledge.py              # 全量索引
  python scripts/index_knowledge.py --incremental # 增量索引
"""

import os
import sys
import argparse

# 确保 src 目录可导入
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from src.rag.embedder.openai_embedder import OpenAIEmbedder
from src.rag.store.chroma_store import ChromaStore
from src.rag.pipeline.index_pipeline import IndexPipeline
from src.rag.config import rag_settings


def main():
    parser = argparse.ArgumentParser(description="电商知识库索引")
    parser.add_argument("--incremental", action="store_true", help="增量索引模式")
    parser.add_argument("--data-dir", default=None, help="知识库数据目录路径")
    args = parser.parse_args()

    data_dir = args.data_dir or str(rag_settings.resolved_data_dir)
    print(f"知识库目录: {data_dir}")
    print(f"向量库目录: {rag_settings.resolved_vector_db_dir}")
    print(f"索引模式: {'增量' if args.incremental else '全量'}")
    print("-" * 50)

    embedder = OpenAIEmbedder()
    store = ChromaStore()
    pipeline = IndexPipeline(embedder, store)

    result = pipeline.run(data_dir, incremental=args.incremental)

    print("-" * 50)
    print(f"索引完成: {result['files']} 个文件, {result['chunks']} 个块")


if __name__ == "__main__":
    main()
