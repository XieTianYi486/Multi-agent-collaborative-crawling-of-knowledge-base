#!/usr/bin/env python3
# ============================================================
# 人工智能学院教学知识库 - 服务器内容同步（幂等，可重复执行）
# 1) 补录 DEFAULT_VIDEOS 中缺失的视频（按 bvid 去重）
# 2) 把 deploy/materials 下的配套资料导入知识库（按 source_hash 去重）
# 用法：KB_APP_DIR=/opt/kb /opt/kb/backend/.venv/bin/python /opt/kb/deploy/sync_content.py
# ============================================================
import hashlib
import os
import shutil
import sys
import traceback
from datetime import date, datetime
from pathlib import Path
from typing import Optional

APP_DIR = Path(os.environ.get("KB_APP_DIR", "/opt/kb")).resolve()
BACKEND_DIR = APP_DIR / "backend"
MATERIALS_DIR = APP_DIR / "deploy" / "materials"
UPLOAD_SUBDIR = "materials_20261109"

sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

from app.db.sqlite import SessionLocal  # noqa: E402
from app.models.document import Category, DocChunk, Document  # noqa: E402
from app.models.user import Role, User  # noqa: E402
from app.models.video import Video  # noqa: E402
from app.services.video_seed import DEFAULT_VIDEOS  # noqa: E402

CATEGORY_BY_FILE = {
    "大模型本地部署实践指南.md": "大模型前沿",
    "AI应用开发实战指南.md": "大模型前沿",
    "AI Agent与多智能体开发指南.md": "智能体与强化学习",
}
TAGS = ["软件工程", "大模型", "教学资料"]


def sync_videos(db) -> None:
    existing = {bvid for (bvid,) in db.query(Video.bvid).all()}
    added = 0
    for item in DEFAULT_VIDEOS:
        if item["bvid"] in existing:
            continue
        db.add(Video(status=1, **item))
        existing.add(item["bvid"])
        added += 1
    db.commit()
    print(f"[videos] 新增 {added} 条，当前共 {db.query(Video).count()} 条")


def resolve_category_id(db, name: str) -> Optional[int]:
    root = db.query(Category).filter(
        Category.name == "AI热点追踪", Category.parent_id == 0
    ).first()
    if root is None:
        return None
    row = db.query(Category).filter(
        Category.name == name, Category.parent_id == root.id
    ).first()
    return row.id if row else None


def admin_user_id(db) -> Optional[int]:
    row = (
        db.query(User)
        .join(Role, User.role_id == Role.id)
        .filter(Role.code.in_(["super_admin", "knowledge_admin"]))
        .order_by(User.id)
        .first()
    )
    return row.id if row else None


def doc_title(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            return line[2:].strip()[:255]
    return path.stem[:255]


def sync_materials(db) -> None:
    from app.rag.ingestion import process_document
    from app.rag.retrievers.bm25_retriever import save_bm25_index

    if not MATERIALS_DIR.is_dir():
        print("[materials] 未找到 deploy/materials，跳过")
        return

    target_dir = BACKEND_DIR / "uploads" / UPLOAD_SUBDIR
    target_dir.mkdir(parents=True, exist_ok=True)

    admin_id = admin_user_id(db)
    existing = {
        h for (h,) in db.query(Document.source_hash).filter(
            Document.source_hash.isnot(None)
        )
    }
    imported = 0
    for path in sorted(MATERIALS_DIR.glob("*.md")):
        source_hash = hashlib.sha256(
            f"{UPLOAD_SUBDIR}:{path.name}".encode("utf-8")
        ).hexdigest()
        if source_hash in existing:
            print(f"[materials] 已存在，跳过：{path.name}")
            continue

        category_name = CATEGORY_BY_FILE.get(path.name)
        category_id = resolve_category_id(db, category_name) if category_name else None
        if category_id is None:
            # 线上分类树可能与本地不同：回退到「AI热点追踪」根分类，避免资料被跳过
            root = db.query(Category).filter(
                Category.name == "AI热点追踪", Category.parent_id == 0
            ).first()
            category_id = root.id if root else None
            print(f"[materials] 未找到子分类，回退分类ID={category_id}：{path.name}")

        target = target_dir / path.name
        if not target.exists():
            shutil.copy2(path, target)

        title = doc_title(target)
        doc = Document(
            title=title,
            file_name=f"{UPLOAD_SUBDIR}/{path.name}",
            file_path=str(target),
            file_size=target.stat().st_size,
            file_type="md",
            category_id=category_id,
            tags=TAGS,
            security_level=1,
            status=0,
            created_by=admin_id,
            publish_date=date.today(),
            source_hash=source_hash,
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)

        chunk_count, chunk_ids, chunk_records = process_document(
            file_path=str(target),
            file_type="md",
            document_id=doc.id,
            title=title,
            category_id=category_id,
            security_level=1,
            persist_index=False,
        )
        for i, chunk_id in enumerate(chunk_ids):
            info = chunk_records[i] if i < len(chunk_records) else {}
            db.add(DocChunk(
                document_id=doc.id,
                chunk_index=i,
                content=info.get("content", ""),
                chapter=info.get("chapter", ""),
                page_start=info.get("page", 1),
                chroma_id=chunk_id,
                token_count=info.get("token_count", 0),
            ))
        doc.chunk_count = chunk_count
        doc.review_status = 2
        doc.reviewed_by = admin_id
        doc.reviewed_at = datetime.now()
        doc.review_comment = "视频专区配套资料，公开教学资料自动审核通过"
        doc.status = 1
        db.commit()
        imported += 1
        print(f"[materials] 已入库：{title}（{chunk_count} 分块）")

    if imported:
        save_bm25_index()
        print("[materials] BM25 索引已持久化")


def main() -> int:
    db = SessionLocal()
    try:
        sync_videos(db)
    except Exception:
        traceback.print_exc()
        print("[videos] 同步失败，继续处理资料")
    try:
        sync_materials(db)
    except Exception:
        traceback.print_exc()
        print("[materials] 同步失败，跳过（不影响服务启动）")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
