"""
SQLite 数据库连接管理

提供 get_db() 获取数据库连接，自动启用外键约束和字典式返回。
数据库文件位于 data/ecommerce.db。
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "ecommerce.db"


def get_db() -> sqlite3.Connection:
    """获取数据库连接"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def dict_from_row(row: sqlite3.Row | None) -> dict | None:
    """将 Row 对象转为字典"""
    if row is None:
        return None
    return dict(row)


def dicts_from_rows(rows: list[sqlite3.Row]) -> list[dict]:
    """将 Row 列表转为字典列表"""
    return [dict(r) for r in rows]
