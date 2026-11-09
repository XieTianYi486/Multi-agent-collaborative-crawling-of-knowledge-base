# ============================================================
# 迁移 Chroma 向量集合名（不重新嵌入）
#
# 背景：项目早期名为 labor_law_docs（劳动法/企业制度知识库），
#      现收敛为嵌入式教学知识库，集合名统一为 teaching_kb_docs。
#      直接改配置会指向空集合，需先把旧集合的向量原样复制到新集合。
#
# 用法：
#   cd backend
#   python scripts/migrate_collection_name.py --dry-run   # 只打印数量
#   python scripts/migrate_collection_name.py             # 实际复制
#
# 说明：复制的是旧集合已有的 embeddings，不会再调用嵌入模型，零 API 成本。
#      若当前部署使用 FAISS 后端（VECTOR_BACKEND=faiss），本脚本无需执行。
# ============================================================

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings  # noqa: E402

OLD_NAME = "labor_law_docs"


def main() -> int:
    parser = argparse.ArgumentParser(description="复制 Chroma 向量集合（不重新嵌入）")
    parser.add_argument("--old", default=OLD_NAME, help=f"旧集合名（默认 {OLD_NAME}）")
    parser.add_argument("--new", default=settings.CHROMA_COLLECTION_NAME,
                        help="新集合名（默认取 CHROMA_COLLECTION_NAME）")
    parser.add_argument("--batch", type=int, default=500, help="每批复制数量")
    parser.add_argument("--dry-run", action="store_true", help="只统计数量，不写入")
    args = parser.parse_args()

    try:
        import chromadb
    except ImportError:
        print("[错误] 未安装 chromadb，无需迁移（FAISS 后端不使用集合名）。")
        return 1

    client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIR)

    try:
        old = client.get_collection(args.old)
    except Exception:
        print(f"[跳过] 未找到旧集合 {args.old}，无需迁移。")
        return 0

    old_count = old.count()
    print(f"[信息] 旧集合 {args.old}：{old_count} 条向量")

    if args.new == args.old:
        print("[跳过] 新旧集合名相同。")
        return 0

    if args.dry_run:
        print(f"[dry-run] 将复制到 {args.new}，未写入。")
        return 0

    new = client.get_or_create_collection(
        name=args.new,
        metadata={"hnsw:space": "cosine"},
    )
    already = new.count()
    if already >= old_count and old_count > 0:
        print(f"[跳过] 新集合已存在且已有 {already} 条，避免重复写入。")
        return 0

    copied = 0
    offset = 0
    while offset < old_count:
        batch = old.get(
            limit=args.batch,
            offset=offset,
            include=["embeddings", "documents", "metadatas"],
        )
        ids = batch.get("ids") or []
        if not ids:
            break
        new.add(
            ids=ids,
            embeddings=batch["embeddings"],
            documents=batch.get("documents"),
            metadatas=batch.get("metadatas"),
        )
        copied += len(ids)
        offset += len(ids)
        print(f"[进度] 已复制 {copied}/{old_count}")

    print(f"[完成] 新集合 {args.new}：{new.count()} 条（本次复制 {copied} 条）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
