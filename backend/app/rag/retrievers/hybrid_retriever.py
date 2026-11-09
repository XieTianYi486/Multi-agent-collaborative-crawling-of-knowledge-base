# ============================================================
# 混合检索器（双路召回 + 加权融合）
# 向量检索 + BM25 关键词检索 → 归一化加权融合
# ============================================================

from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Optional, Tuple

from app.core.config import settings
from app.rag.retrievers.vector_retriever import get_vector_retriever
from app.rag.retrievers.bm25_retriever import get_bm25_retriever
from app.rag.retrievers.source_authority import (
    get_source_authority, authority_label,
)


class HybridRetriever:
    """
    混合检索器

    流程：
    1. 并行执行向量检索和 BM25 检索
    2. 融合两路结果（weighted=归一化加权；rrf=倒数排名融合）
    3. 去重（按 chunk_id）
    4. 排序返回 Top-K

    权重和 Top-K 参数从配置读取，支持运行时热更新。
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
        fusion_strategy: Optional[str] = None,
    ) -> List[Dict]:
        """
        混合检索

        参数:
            query: 用户问题
            top_k: 融合后返回数量（默认 FUSION_TOP_K）
            security_level: 密级过滤
            fusion_strategy: 融合策略（weighted / rrf），默认取 FUSION_STRATEGY

        返回:
            [{"chunk_id": str, "content": str, "document_name": str,
              "chapter": str, "page": int, "score": float, "source": str}, ...]
        """
        if top_k is None:
            top_k = settings.FUSION_TOP_K

        # ===== 双路召回并行：向量语义检索（含 embedding 网络请求）+ BM25 关键词检索 =====
        with ThreadPoolExecutor(max_workers=2) as executor:
            vector_future = executor.submit(
                self.vector_retriever.search,
                query=query,
                top_k=settings.VECTOR_TOP_K,
                security_level=security_level,
            )
            bm25_future = executor.submit(
                self.bm25_retriever.search,
                query=query,
                top_k=settings.BM25_TOP_K,
                security_level=security_level,
            )
            vector_results = vector_future.result()
            bm25_results = bm25_future.result()

        # ===== 融合 =====
        merged = self._merge_results(
            vector_results, bm25_results, fusion_strategy or settings.FUSION_STRATEGY
        )

        # ===== 来源权威度加权（官方文档优先于论坛/转载）=====
        self._apply_source_authority(merged)

        # 排序并返回 Top-K
        merged.sort(key=lambda x: x["score"], reverse=True)
        return merged[:top_k]

    @staticmethod
    def _apply_source_authority(chunks: List[Dict]) -> None:
        """
        按来源域名解析权威度并乘到融合分数上（原地修改）。

        权威度来自爬虫站点档案 authority_weight（官方文档 1.3~1.4，
        论坛/转载 0.7~1.0），使同等相关性下权威来源排前。
        """
        for c in chunks:
            weight, site = get_source_authority(c.get("source_url", ""))
            if weight != 1.0:
                c["score"] = round(c.get("score", 0) * weight, 6)
            c["authority_weight"] = weight
            c["authority_label"] = authority_label(weight)
            c["source_site"] = site

    def _merge_results(
        self,
        vector_results: List[Dict],
        bm25_results: List[Tuple[Dict, float]],
        fusion_strategy: str = "weighted",
    ) -> List[Dict]:
        """融合向量和 BM25 检索结果"""
        if fusion_strategy == "rrf":
            return self._merge_rrf(vector_results, bm25_results, settings.RRF_K)

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

    def _merge_rrf(
        self,
        vector_results: List[Dict],
        bm25_results: List[Tuple[Dict, float]],
        k: int,
    ) -> List[Dict]:
        """倒数排名融合（RRF）：只使用排名，不依赖两路分数的绝对尺度"""
        chunk_map: Dict[str, Dict] = {}

        def add(item: Dict, rank: int, source: str) -> None:
            cid = item.get("chunk_id", "")
            if not cid:
                return
            score = 1.0 / (k + rank)
            if cid in chunk_map:
                chunk_map[cid]["score"] += score
                chunk_map[cid]["source"] = "hybrid"
                return
            chunk_map[cid] = {
                "chunk_id": cid,
                "content": item.get("content", ""),
                "document_id": item.get("document_id", 0),
                "document_name": item.get("document_name", ""),
                "chapter": item.get("chapter", ""),
                "page": item.get("page", 1),
                "source_url": item.get("source_url", ""),
                "score": score,
                "source": source,
            }

        for rank, r in enumerate(vector_results, start=1):
            add(r, rank, "vector")
        for rank, (chunk, _score) in enumerate(bm25_results, start=1):
            add(chunk, rank, "bm25")

        return list(chunk_map.values())


# --- 全局单例 ---
_hybrid_retriever: Optional[HybridRetriever] = None


def get_hybrid_retriever() -> HybridRetriever:
    """获取混合检索器单例"""
    global _hybrid_retriever
    if _hybrid_retriever is None:
        _hybrid_retriever = HybridRetriever()
    return _hybrid_retriever
