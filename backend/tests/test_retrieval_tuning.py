# ============================================================
# 检索调优逻辑测试
# 覆盖：RRF 融合、加权融合回退、条件改写判定
# ============================================================

import pytest

from app.core.config import settings
from app.rag.query_processor.query_rewrite import should_rewrite
from app.rag.retrievers.hybrid_retriever import HybridRetriever


def _chunk(cid: str) -> dict:
    return {
        "chunk_id": cid,
        "content": f"内容-{cid}",
        "document_id": 1,
        "document_name": "测试文档",
        "chapter": "测试章节",
        "page": 1,
        "source_url": "",
    }


def _retriever() -> HybridRetriever:
    """跳过 __init__ 的外部依赖，仅测试融合逻辑"""
    return HybridRetriever.__new__(HybridRetriever)


def test_rrf_uses_rank_not_score_scale():
    """RRF 只依赖排名：向量分数被整体放大也不影响融合结果"""
    retriever = _retriever()
    vector_results = [
        {**_chunk("a"), "score": 10.0},
        {**_chunk("b"), "score": 9.0},
    ]
    bm25_results = [
        (_chunk("b"), 100.0),
        (_chunk("c"), 1.0),
    ]

    merged = {c["chunk_id"]: c for c in retriever._merge_results(
        vector_results, bm25_results, "rrf"
    )}

    assert merged["a"]["score"] == 1 / (settings.RRF_K + 1)
    assert merged["b"]["score"] == 1 / (settings.RRF_K + 1) + 1 / (settings.RRF_K + 2)
    assert merged["c"]["score"] == 1 / (settings.RRF_K + 2)
    # b 两路都命中，标记为 hybrid
    assert merged["b"]["source"] == "hybrid"
    assert merged["a"]["source"] == "vector"
    assert merged["c"]["source"] == "bm25"


def test_weighted_fusion_still_default():
    """weighted 策略保持原语义：两路都命中的片段累加归一化分数"""
    retriever = _retriever()
    vector_results = [
        {**_chunk("a"), "score": 0.9},
        {**_chunk("b"), "score": 0.1},
    ]
    bm25_results = [(_chunk("a"), 2.0)]

    merged = {c["chunk_id"]: c for c in retriever._merge_results(
        vector_results, bm25_results, "weighted"
    )}

    assert merged["a"]["score"] == 1.0
    assert merged["a"]["source"] == "hybrid"
    assert merged["b"]["score"] == pytest.approx(0.1 / 0.9 * 0.5)


def test_should_rewrite_conditional(monkeypatch):
    monkeypatch.setattr(settings, "QUERY_REWRITE_MODE", "conditional")
    monkeypatch.setattr(settings, "QUERY_REWRITE_MIN_CHARS", 16)

    # 表述完整的长问题：跳过改写
    assert should_rewrite("ESP32 芯片一共有多少个物理 GPIO 管脚？") is False
    # 短问题：改写
    assert should_rewrite("GPIO 怎么配置") is True
    # 指代：改写
    assert should_rewrite("它的引脚定义是什么，和刚才那个模块一样吗") is True
    # 带对话历史：改写
    assert should_rewrite("那它的默认值是多少", [{"role": "user", "content": "ADC" }]) is True


def test_should_rewrite_modes(monkeypatch):
    question = "ESP-IDF 中 gpio_config 的参数结构体包含哪些字段？"

    monkeypatch.setattr(settings, "QUERY_REWRITE_MODE", "off")
    assert should_rewrite(question) is False

    monkeypatch.setattr(settings, "QUERY_REWRITE_MODE", "always")
    assert should_rewrite(question) is True
