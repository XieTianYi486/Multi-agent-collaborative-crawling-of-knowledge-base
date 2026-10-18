# ============================================================
# 导员知识库检索器（自包含，与教学知识库索引完全隔离）
#
# 设计要点：
# - 数据源来自 counselor_kb_chunks 表（按"条"切分的校规/学术规范）
# - 向量部分：条款 embedding 以 JSON 落库，启动时加载到内存做余弦检索
# - 关键词部分：复用 BM25Retriever，但实例独立、不共享主知识库单例
# - 命中判定使用"绝对余弦相似度"，避免最大值归一化的天花板效应
#   （相对归一化下的第一名恒得满分，无法作为拒答阈值）
# ============================================================

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np

from app.core.config import settings
from app.db.sqlite import SessionLocal
from app.models.counselor import CounselorKbChunk
from app.rag.retrievers.bm25_retriever import BM25Retriever

logger = logging.getLogger(__name__)


class CounselorRetriever:
    """导员知识库混合检索器（内存索引，独立于主知识库）"""

    def __init__(self):
        self._bm25 = BM25Retriever()
        self._chunks: List[Dict] = []
        self._emb_matrix: Optional[np.ndarray] = None
        self._loaded = False

    # ---------- 加载 ----------

    def reload(self) -> None:
        """强制重新加载（导员知识库重新导入后调用）"""
        self._loaded = False
        self._load()

    def _load(self) -> None:
        if self._loaded:
            return

        db = SessionLocal()
        try:
            rows = (
                db.query(CounselorKbChunk)
                .order_by(CounselorKbChunk.id.asc())
                .all()
            )
        finally:
            db.close()

        chunks: List[Dict] = []
        embeddings: List[Optional[List[float]]] = []
        for r in rows:
            chunks.append({
                "chunk_id": f"ck_{r.id}",
                "content": r.content,
                "source_title": r.source_title,
                "document_name": r.source_title,
                "article_no": r.article_no or "",
                "chapter": r.chapter or "",
                "source_url": r.source_url or "",
            })
            embeddings.append(list(r.embedding) if r.embedding else None)

        self._chunks = chunks
        if chunks:
            # BM25 仅依赖 content 字段
            self._bm25.build_index(chunks)

        # 仅当所有条款都有向量时才构建向量矩阵（否则退化为纯 BM25）
        if chunks and all(e is not None for e in embeddings):
            matrix = np.array(embeddings, dtype=np.float32)
            norms = np.linalg.norm(matrix, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            self._emb_matrix = matrix / norms
        else:
            self._emb_matrix = None

        self._loaded = True
        logger.info(
            "导员知识库加载完成：%d 条条款，向量索引=%s",
            len(chunks), "启用" if self._emb_matrix is not None else "未启用",
        )

    @property
    def is_empty(self) -> bool:
        self._load()
        return len(self._chunks) == 0

    # ---------- 检索 ----------

    def search(self, query: str, top_k: Optional[int] = None) -> List[Dict]:
        """
        混合检索导员知识库，返回按融合分降序的条款列表。

        每个结果额外携带：
        - cosine: 绝对余弦相似度（无向量索引时为 None）
        - bm25_norm: BM25 相对归一化分
        """
        self._load()
        if not self._chunks:
            return []
        if top_k is None:
            top_k = settings.COUNSELOR_TOP_K

        vector_hits = self._vector_search(query, top_k)
        bm25_hits = self._bm25.search(query, top_k=top_k, security_level=None)

        merged: Dict[str, Dict] = {}

        # 向量路：记录绝对余弦
        for chunk, cos in vector_hits:
            cid = chunk["chunk_id"]
            merged[cid] = {**chunk, "score": 0.0, "cosine": cos, "bm25_norm": 0.0}

        # BM25 路：记录归一化分
        for chunk, norm in bm25_hits:
            cid = chunk.get("chunk_id", "")
            if cid in merged:
                merged[cid]["bm25_norm"] = norm
            else:
                merged[cid] = {
                    **chunk, "score": 0.0, "cosine": None, "bm25_norm": norm,
                }

        # 融合分仅用于展示；排序以"绝对余弦"为主，BM25 归一化分为辅。
        # 原因：BM25 采用最大值归一化，只要有任何字重叠其 top 分即≈1.0，
        # 若以融合分排序会把字面重叠的无关条款顶到前面，反而把真正高余弦的
        # 条款挤出 top_k，导致命中判定取到的最大余弦偏低而漏判。
        for item in merged.values():
            cos = item.get("cosine")
            vec_part = cos if cos is not None else 0.0
            item["score"] = round(0.5 * vec_part + 0.5 * item["bm25_norm"], 4)

        ranked = sorted(
            merged.values(),
            key=lambda x: (
                -(x["cosine"] if x.get("cosine") is not None else -1.0),
                -(x.get("bm25_norm") or 0.0),
            ),
        )
        return ranked[:top_k]

    def _vector_search(self, query: str, top_k: int) -> List[Tuple[Dict, float]]:
        """内存向量检索，返回 (chunk, 绝对余弦相似度) 列表；不可用时返回空"""
        if self._emb_matrix is None:
            return []
        from app.rag.embeddings.dashscope_embeddings import get_embeddings

        q_vec: Optional[List[float]] = None
        for attempt in range(2):  # 嵌入接口偶发失败，重试一次
            try:
                q_vec = get_embeddings().embed_query(query)
                break
            except Exception as e:
                if attempt == 0:
                    logger.warning("导员知识库向量检索重试（embedding 失败）：%s", e)
                else:
                    logger.warning("导员知识库向量检索降级（embedding 持续失败）：%s", e)
        if not q_vec:
            return []

        q = np.array(q_vec, dtype=np.float32)

        norm = float(np.linalg.norm(q))
        if norm == 0:
            return []
        q = q / norm

        sims = self._emb_matrix @ q  # 余弦相似度，范围约 [-1, 1]
        order = np.argsort(-sims)[:top_k]
        return [(self._chunks[i], float(sims[i])) for i in order]


# --- 全局单例 ---
_counselor_retriever: Optional[CounselorRetriever] = None


def get_counselor_retriever() -> CounselorRetriever:
    """获取导员知识库检索器单例"""
    global _counselor_retriever
    if _counselor_retriever is None:
        _counselor_retriever = CounselorRetriever()
    return _counselor_retriever
