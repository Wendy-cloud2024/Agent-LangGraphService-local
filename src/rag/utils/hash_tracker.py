"""
文件哈希变更检测

用于增量索引时判断哪些文件是新增/修改/删除的。
"""

import hashlib
import json
from pathlib import Path


class HashTracker:
    """追踪文件 Hash，用于增量索引"""

    def __init__(self, db_path: str = "index/file_hashes.json"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def compute_hash(self, filepath: str | Path) -> str:
        """计算文件 SHA-256"""
        h = hashlib.sha256()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    def load(self) -> dict[str, str]:
        if self.db_path.exists():
            with open(self.db_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def save(self, db: dict[str, str]):
        with open(self.db_path, "w", encoding="utf-8") as f:
            json.dump(db, f, indent=2, ensure_ascii=False)

    def detect_changes(self, current_files: set[str]) -> dict:
        """
        对比当前文件集合与历史 Hash，返回变更信息。
        返回 {"added": [...], "modified": [...], "deleted": [...], "new_db": {...}}
        """
        old_db = self.load()
        new_db = {}
        added, modified = [], []

        for filepath in current_files:
            file_hash = self.compute_hash(filepath)
            new_db[filepath] = file_hash

            if filepath not in old_db:
                added.append(filepath)
            elif old_db[filepath] != file_hash:
                modified.append(filepath)

        deleted = [f for f in old_db if f not in current_files]

        return {
            "added": added,
            "modified": modified,
            "deleted": deleted,
            "new_db": new_db,
        }
