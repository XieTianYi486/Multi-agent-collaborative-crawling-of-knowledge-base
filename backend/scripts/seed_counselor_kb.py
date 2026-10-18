# ============================================================
# 导员知识库导入脚本
#
# 用法（在 backend 目录下执行）：
#     python scripts/seed_counselor_kb.py
#
# 作用：读取 data/counselor_kb/*.md（校规/学术规范），按"条"切分后
#       写入 counselor_kb_chunks 表并计算条款向量。可重复执行（重建）。
# ============================================================

import os
import sys

# 确保可以导入 app 包（脚本可能在任意工作目录下执行）
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.db.sqlite import init_db, SessionLocal  # noqa: E402
from app.models.counselor import CounselorKbChunk  # noqa: E402
from app.rag.counselor_ingest import ingest_counselor_kb  # noqa: E402


def main():
    print("[导员知识库] 初始化数据库表...")
    init_db()

    print("[导员知识库] 开始导入校规/学术规范文档...")
    result = ingest_counselor_kb(rebuild=True, with_embeddings=True)
    print(
        f"[导员知识库] 完成：文件 {result['files']} 个，"
        f"条款 {result['articles']} 条，已向量化 {result['embedded']} 条"
    )

    db = SessionLocal()
    try:
        total = db.query(CounselorKbChunk).count()
        print(f"[导员知识库] counselor_kb_chunks 现有条款：{total} 条")
    finally:
        db.close()


if __name__ == "__main__":
    main()
