# -*- coding: utf-8 -*-
"""
向量索引一致性修复脚本（零批量 API 成本）

问题：
1. 幽灵向量：索引里有、主库 doc_chunks 已无的向量（删除/归档文档残留）；
2. 缺失分块：主库有、索引里没有的分块（该文档向量召回永远失败）；
3. doc_chunks 重复行：同 chroma_id 出现多行（历史重建 bug 残留，只报告不删除）。

修复方式：
- 不重跑全量 embedding（2.3 万块 × API 成本不可接受）；
- 用 faiss.reconstruct 从现有索引按序取回有效向量 → 原地重建 IndexFlatIP；
- 只对"主库有、索引缺"的分块调用 embedding；缺失超过 50 个时需 --yes 确认
  （批量 embedding 产生 API 费用，须显式同意）；
- 同步重建 meta.sqlite3 与 BM25 索引，字段集合与 app/rag/ingestion.py 对齐
  （含 source_url —— 答案"原文链接"与来源权威权重的依赖字段）。

用法: python fix_vector_index.py [--yes]
仅适用 FAISS 向量后端（ChromaDB 后端请勿运行）。
执行前自动备份旧索引文件；完成后需重启后端生效。
"""
import argparse
import json
import os
import sys
import time

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import sqlite3

import faiss
import numpy as np

from app.core.config import settings
from app.db.sqlite import SessionLocal
from app.models.document import DocChunk, Document
from app.rag.embeddings.dashscope_embeddings import get_embeddings
from app.rag.retrievers.bm25_retriever import BM25Retriever, BM25_INDEX_PATH

# 缺失分块超过该数量时，需要 --yes 显式确认（批量 embedding 产生 API 费用）
EMBED_CONFIRM_THRESHOLD = 50


def _fail(message: str) -> None:
    print(f"✗ {message}")
    sys.exit(1)


def main() -> None:
    """向量索引一致性修复主流程（详见模块 docstring）。"""
    parser = argparse.ArgumentParser(description="向量索引一致性修复")
    parser.add_argument("--yes", action="store_true",
                        help=f"缺失分块超过 {EMBED_CONFIRM_THRESHOLD} 个时仍继续（将产生 embedding API 费用）")
    args = parser.parse_args()

    print("=" * 60)
    print("向量索引一致性修复")
    print("=" * 60)

    faiss_dir = os.path.join(settings.CHROMA_PERSIST_DIR, "faiss_index")
    index_file = os.path.join(faiss_dir, "index.faiss")
    meta_file = os.path.join(faiss_dir, "meta.sqlite3")

    if not os.path.exists(index_file):
        _fail(f"未找到 FAISS 索引 {index_file}。本脚本仅适用 FAISS 向量后端；"
              "ChromaDB 后端请使用其他迁移工具。")

    # ---------- 1. 读主库：有效分块（去重后） ----------
    db = SessionLocal()
    try:
        docs = {d.id: d for d in db.query(Document).all()}
        all_chunks = (
            db.query(DocChunk)
            .order_by(DocChunk.document_id, DocChunk.chunk_index)
            .all()
        )
    finally:
        db.close()
    # 按 chroma_id 去重（重复行内容相同，保留先出现的行）
    best: dict[str, DocChunk] = {}
    dup_rows: list[int] = []
    for c in all_chunks:
        cid = c.chroma_id
        if cid in best:
            dup_rows.append(c.id)
        else:
            best[cid] = c
    db_chunk_ids = set(best.keys())
    print(f"主库分块行: {len(all_chunks)}，唯一 chroma_id: {len(best)}，重复行: {len(dup_rows)}")

    # ---------- 2. 读现有索引 ----------
    index = faiss.read_index(index_file)
    meta = sqlite3.connect(meta_file)
    meta_rows = {
        row[1]: (row[0], row[2], row[3])  # chunk_id -> (idx, doc, meta_json)
        for row in meta.execute("SELECT idx, chunk_id, doc, meta FROM chunks")
    }
    # 必须立即关闭：Windows 下打开句柄会阻止后面备份时重命名目录
    meta.close()
    print(f"现有索引向量: {index.ntotal}，meta 行: {len(meta_rows)}")
    if index.ntotal != len(meta_rows):
        _fail("索引与 meta 行数不一致，请先人工排查（不要继续运行）")

    ghosts = sorted(set(meta_rows) - db_chunk_ids)
    missing = sorted(db_chunk_ids - set(meta_rows))
    print(f"幽灵向量（主库已无）: {len(ghosts)}")
    for g in ghosts[:10]:
        print(f"    {g}")
    print(f"缺失分块（索引里没有）: {len(missing)}")
    for m in missing:
        print(f"    {m}")

    if len(missing) > EMBED_CONFIRM_THRESHOLD and not args.yes:
        _fail(f"缺失分块 {len(missing)} 个，补齐需要 {len(missing)} 次 embedding API 调用（产生费用）。"
              f"确认后加 --yes 重新运行。")

    # ---------- 3. 取回有效向量，补缺失分块的 embedding ----------
    keep = [cid for cid, (idx, _, _) in meta_rows.items() if cid in db_chunk_ids]
    keep_idx = [meta_rows[cid][0] for cid in keep]
    print(f"保留向量: {len(keep_idx)}")

    # 分块取回，避免一次性 reconstruct 全部向量撑爆内存
    vectors = np.empty((len(keep_idx), index.d), dtype=np.float32)
    batch = 4096
    for i in range(0, len(keep_idx), batch):
        group = keep_idx[i:i + batch]
        vectors[i:i + len(group)] = np.stack(
            [index.reconstruct(int(idx)) for idx in group]
        )
        print(f"  [取回向量 {min(i + batch, len(keep_idx))}/{len(keep_idx)}]")

    extra_texts = [best[cid].content for cid in missing]
    if extra_texts:
        embeddings_client = get_embeddings()
        extra_vecs = embeddings_client.embed_documents(extra_texts)
        print(f"补齐缺失分块 embedding: {len(extra_vecs)} 个")

    all_cids = keep + missing
    if extra_texts:
        all_vecs = np.vstack([vectors, np.array(extra_vecs, dtype=np.float32)])
    else:
        all_vecs = vectors
    faiss.normalize_L2(all_vecs)

    # ---------- 4. 备份旧索引（失败自动回滚） ----------
    backup_suffix = time.strftime("%Y%m%d_%H%M%S")
    backups: list[tuple[str, str]] = []
    try:
        for path in (faiss_dir, BM25_INDEX_PATH):
            if os.path.exists(path):
                backup = f"{path}.bak_{backup_suffix}"
                os.rename(path, backup)
                backups.append((path, backup))
                print(f"已备份: {backup}")
    except OSError:
        # 半迁移状态回滚：把已改名的再改回来
        for path, backup in reversed(backups):
            try:
                os.rename(backup, path)
            except OSError:
                pass
        _fail("备份失败（可能有进程占用索引文件，请先停止后端），已回滚")

    # ---------- 5. 写回新索引 + 新 meta ----------
    try:
        os.makedirs(faiss_dir, exist_ok=True)  # 备份时目录已被改名移走，先重建
        new_index = faiss.IndexFlatIP(index.d)
        new_index.add(all_vecs)
        faiss.write_index(new_index, index_file)
        new_meta = sqlite3.connect(meta_file)
        new_meta.execute("PRAGMA journal_mode=WAL;")
        new_meta.execute(
            """CREATE TABLE IF NOT EXISTS chunks (
                idx INTEGER PRIMARY KEY,
                chunk_id TEXT UNIQUE NOT NULL,
                doc TEXT,
                meta TEXT
            )"""
        )
        new_meta.execute("DELETE FROM chunks")
        bm_chunks = []
        for i, cid in enumerate(all_cids):
            c = best[cid]
            doc = docs.get(c.document_id)
            meta_obj = {
                "document_id": c.document_id,
                "document_name": doc.title if doc else "",
                "chapter": c.chapter or "",
                "page": c.page_start or 1,
                "security_level": doc.security_level if doc else 1,
                "category_id": doc.category_id or 0,
                "token_count": c.token_count or 0,
                "chunk_index": c.chunk_index,
                # 字段集合与 app/rag/ingestion.py 对齐：source_url 是答案"原文链接"
                # 与来源权威权重（hybrid_retriever）的依赖字段，漏写会导致
                # 爬虫入库分块静默丢失溯源
                "source_url": (doc.source_url or "") if doc else "",
            }
            new_meta.execute(
                "INSERT INTO chunks (idx, chunk_id, doc, meta) VALUES (?, ?, ?, ?)",
                (i, cid, c.content, json.dumps(meta_obj, ensure_ascii=False)),
            )
            bm_chunks.append({
                "chunk_id": cid,
                "document_id": c.document_id,
                "document_name": doc.title if doc else "",
                "chapter": c.chapter or "",
                "page": c.page_start or 1,
                "content": c.content,
                "security_level": doc.security_level if doc else 1,
                "token_count": c.token_count or 0,
                "source_url": (doc.source_url or "") if doc else "",
            })
        new_meta.commit()
        new_meta.close()
        print(f"新 FAISS 索引: {new_index.ntotal} 个向量（原 {index.ntotal}，删幽灵 {len(ghosts)}，补缺失 {len(missing)}）")

        # ---------- 6. 重建 BM25 ----------
        bm = BM25Retriever()
        bm.build_index(bm_chunks)
        bm.save(BM25_INDEX_PATH)
        print(f"BM25 索引重建: {bm.chunk_count} 个分块")
    except Exception:
        # 写回失败：恢复备份，保持"要么全成、要么原样"
        for path, backup in reversed(backups):
            try:
                if os.path.exists(path):
                    if os.path.isdir(path):
                        import shutil
                        shutil.rmtree(path)
                    else:
                        os.remove(path)
                os.rename(backup, path)
            except OSError:
                pass
        raise

    # ---------- 7. 重复分块行（只报告，不自动删除） ----------
    # doc_chunks 重复行不影响检索（索引按唯一 chroma_id 构建），
    # 仅造成统计虚高；删除属不可逆操作，需单独征得确认：
    # 在备份 enterprise_rag.db 后按 chroma_id 保留 id 最小行即可。
    if dup_rows:
        print(f"[提示] 检测到 {len(dup_rows)} 行重复分块记录（内容相同，不影响检索），未自动删除")

    # ---------- 8. 验证 ----------
    print("\n验证:")
    check = faiss.read_index(index_file)
    check_meta = sqlite3.connect(meta_file)
    rows = check_meta.execute("SELECT chunk_id FROM chunks").fetchall()
    check_ids = {r[0] for r in rows}
    check_meta.close()
    if check.ntotal != len(check_ids):
        _fail("重建后索引与 meta 行数不一致")
    if check_ids != db_chunk_ids:
        _fail("重建后与主库分块不一致（存在幽灵或缺失）")
    print(f"✓ FAISS={check.ntotal} 主库={len(db_chunk_ids)} 完全一致（无幽灵、无缺失）")
    print("\n✓ 修复完成。请重启后端服务使新索引生效。")


if __name__ == "__main__":
    main()
