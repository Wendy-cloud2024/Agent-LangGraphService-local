"""
电商数据库初始化脚本

用法:
  python scripts/init_db.py           # 建表 + 灌种子数据
  python scripts/init_db.py --reset   # 删除重建
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from src.db.connection import get_db, DB_PATH


def init_db(reset: bool = False):
    """初始化数据库"""
    if reset and DB_PATH.exists():
        DB_PATH.unlink()
        print(f"已删除旧数据库: {DB_PATH}")

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    # 读取 schema.sql 建表
    schema_path = Path(__file__).resolve().parent.parent / "src" / "db" / "schema.sql"
    schema_sql = schema_path.read_text(encoding="utf-8")

    db = get_db()
    db.executescript(schema_sql)
    db.close()
    print(f"数据库已创建: {DB_PATH}")

    # 灌种子数据
    from src.db.seed import seed_all
    seed_all()

    # 验证
    db = get_db()
    tables = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    for t in tables:
        name = t["name"]
        count = db.execute(f"SELECT COUNT(*) as c FROM {name}").fetchone()["c"]
        print(f"  {name}: {count} 条记录")
    db.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="删除重建")
    args = parser.parse_args()
    init_db(reset=args.reset)
