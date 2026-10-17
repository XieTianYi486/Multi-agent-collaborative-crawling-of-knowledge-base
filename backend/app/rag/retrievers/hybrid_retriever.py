# ============================================================
# 混合检索器（双路召回 + 加权融合）
# 向量检索 + BM25 关键词检索 → 归一化加权融合
# ============================================================

from typing import List, Dict, Optional, Tuple

from app.core.config import settings
from app.rag.retrievers.vector_retriever import get_vector_retriever
from app.rag.retrievers.bm25_retriever import get_bm25_retriever


class HybridRetriever:
    """
    混合检索器

    流程：
    1. 并行执行向量检索和 BM25 检索
    2. 分数归一化到 [0, 1]
    3. 加权融合：vector_weight * vector_score + bm25_weight * bm25_score
    4. 去重（按 chunk_id）
    5. 排序返回 Top-K

    权重和 Top-K 参数从数据库动态配置读取，支持运行时热更新。
    """

    def __init__(self):
        self.vector_retriever = get_vector_retriever()
        self.bm25_retriever = get_bm25_retriever()

    @property
    def vector_weight(self) -> float:
        return settings.VECTOR_WEIGHT

    @property
    def bm25_weight(self) -> float:
        return settings.BM25_WEIGHT

    def search(
        self,
        query: str,
        top_k: Optional[int] = None,
        security_level: Optional[int] = None,
    ) -> List[Dict]:
        """
        混合检索

        参数:
            query: 用户问题
            top_k: 融合后返回数量（默认 FUSION_TOP_K）
            security_level: 密级过滤

        返回:
            [{"chunk_id": str, "content": str, "document_name": str,
              "chapter": str, "page": int, "score": float, "source": str}, ...]
        """
        if top_k is None:
            top_k = settings.FUSION_TOP_K

        # ===== 第一路：向量检索 =====
        vector_results = self.vector_retriever.search(
            query=query,
            top_k=settings.VECTOR_TOP_K,
            security_level=security_level,
        )

        # ===== 第二路：BM25 检索 =====
        bm25_results = self.bm25_retriever.search(
            query=query,
            top_k=settings.BM25_TOP_K,
            security_level=security_level,
        )

        # ===== 融合 =====
        merged = self._merge_results(vector_results, bm25_results)

        # 排序并返回 Top-K
        merged.sort(key=lambda x: x["score"], reverse=True)
        return merged[:top_k]

    def _merge_results(
        self,
        vector_results: List[Dict],
        bm25_results: List[Tuple[Dict, float]],
    ) -> List[Dict]:
        """融合向量和 BM25 检索结果"""
        chunk_map: Dict[str, Dict] = {}

        # 处理向量检索结果
        max_vector_score = max(
            (r["score"] for r in vector_results), default=1.0
        )
        for r in vector_results:
            cid = r["chunk_id"]
            norm_score = r["score"] / max_vector_score if max_vector_score > 0 else 0
            chunk_map[cid] = {
                "chunk_id": cid,
                "content": r["content"],
                "document_id": r.get("document_id", 0),
                "document_name": r.get("document_name", ""),
                "chapter": r.get("chapter", ""),
                "page": r.get("page", 1),
                "source_url": r.get("source_url", ""),
                "score": self.vector_weight * norm_score,
                "source": "vector",
            }

        # 处理 BM25 检索结果
        max_bm25_score = max(
            (s for _, s in bm25_results), default=1.0
        )
        for chunk, bm25_score in bm25_results:
            cid = chunk.get("chunk_id", "")
            norm_score = bm25_score / max_bm25_score if max_bm25_score > 0 else 0
            weighted_score = self.bm25_weight * norm_score

            if cid in chunk_map:
                # 两路都召回了，累加分数
                chunk_map[cid]["score"] += weighted_score
                chunk_map[cid]["source"] = "hybrid"
            else:
                chunk_map[cid] = {
                    "chunk_id": cid,
                    "content": chunk.get("content", ""),
                    "document_id": chunk.get("document_id", 0),
                    "document_name": chunk.get("document_name", ""),
                    "chapter": chunk.get("chapter", ""),
                    "page": chunk.get("page", 1),
                    "source_url": chunk.get("source_url", ""),
                    "score": weighted_score,
                    "source": "bm25",
                }

        return list(chunk_map.values())


# --- 全局单例 ---
_hybrid_retriever: Optional[HybridRetriever] = None


def get_hybrid_retriever() -> HybridRetriever:
    """获取混合检索器单例"""
    global _hybrid_retriever
    if _hybrid_retriever is None:
        _hybrid_retriever = HybridRetriever()
    return _hybrid_retriever
