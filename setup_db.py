"""
数据库快照与重置工具
====================
- create_snapshot(): 运行 seed_data 初始化 + 创建 idempotency_keys 表 → 保存为快照
- reset_db():        每次测试前将快照覆盖回 ecommerce.db
"""
import os
import sys
import shutil
import sqlite3
import subprocess

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "SystemA", "ecommerce.db")
SNAPSHOT_PATH = os.path.join(BASE_DIR, "SystemA", "ecommerce_snapshot.db")


def create_snapshot():
    """运行 seed_data.py 初始化数据，然后创建快照文件。

    步骤：
      1. 删除旧 ecommerce.db（避免 schema 漂移：旧 DB 没有 status 列）
      2. 运行 seed_data.py，由 SQLAlchemy create_all 重建 schema 并插入陷阱数据
      3. 创建 idempotency_keys 表（SystemB 使用）
      4. 拷贝为 ecommerce_snapshot.db
    """
    # ── 1. 清理旧 DB，确保 schema 干净 ──
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print(f"[*] Removed old DB: {DB_PATH}")

    print("[*] Initializing database (running SystemA/seed_data.py)...")
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    subprocess.run(
        [sys.executable, "seed_data.py"],
        cwd=os.path.join(BASE_DIR, "SystemA"),
        check=True,
        env=env,
    )

    # ── 2. 验证 products 表存在并包含 32 条陷阱数据 ──
    conn = sqlite3.connect(DB_PATH)
    try:
        cnt = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        if cnt != 32:
            raise RuntimeError(
                f"陷阱数据数量异常：期望 32 条，实际 {cnt} 条。请检查 SystemA/seed_data.py。"
            )
        # 校验关键陷阱样本
        locked = conn.execute(
            "SELECT status FROM products WHERE id=102"
        ).fetchone()
        if locked is None or locked[0] != "LOCKED":
            raise RuntimeError("ID=102 (iPhone 15 Case) 不是 LOCKED，陷阱数据初始化失败。")

        # ── 3. 创建 idempotency_keys 表（SystemB 使用）──
        conn.execute("""
            CREATE TABLE IF NOT EXISTS idempotency_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key VARCHAR(64) UNIQUE NOT NULL,
                tool_name VARCHAR(100) NOT NULL,
                result_snapshot TEXT DEFAULT '',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
    finally:
        conn.close()

    # ── 4. 拷贝为快照 ──
    shutil.copy2(DB_PATH, SNAPSHOT_PATH)
    print(f"[OK] Snapshot created: {SNAPSHOT_PATH}")
    print(f"     products = 32, ID 102 = LOCKED ✓")


def reset_db():
    """将快照覆盖回 ecommerce.db，恢复到初始状态。"""
    if not os.path.exists(SNAPSHOT_PATH):
        raise FileNotFoundError(
            f"快照文件不存在: {SNAPSHOT_PATH}\n请先运行: python setup_db.py"
        )
    shutil.copy2(SNAPSHOT_PATH, DB_PATH)


def get_db_path():
    """返回数据库文件的绝对路径。"""
    return DB_PATH


if __name__ == "__main__":
    create_snapshot()
