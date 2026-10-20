# ============================================================
# AI 导员 服务层 —— 人设陪伴 + 导员知识库作答 双模式编排
#
# 关键设计（"不编造校规"的机制保障）：
#   1. 先检索"导员知识库"（独立索引，不碰教学知识库）
#   2. 命中阈值（绝对余弦）以上 → 知识模式：把条款作为【参考资料】交给 LLM 严格作答
#   3. 未命中 → 陪伴模式：不做事务性断言，只做共情引导，并提示线下核实
#   两条路径都注入"温柔有耐心"的人设，且系统提示中明令禁止编造具体校规
# ============================================================

import logging
import time
import traceback
from typing import AsyncGenerator, Dict, List, Optional

from app.core.config import settings
from app.core.exceptions import LLMException
from app.db.sqlite import SessionLocal
from app.models.counselor import CounselorLog
from app.rag.llm.dashscope_llm import get_llm
from app.rag.prompts.counselor_prompt import (
    build_counselor_messages,
    get_counselor_greeting,
    is_counselor_greeting,
)
from app.rag.retrievers.counselor_retriever import get_counselor_retriever

logger = logging.getLogger(__name__)


class CounselorService:
    """导员服务（人设 + 知识库双模式，独立于教学问答 RAG 链路）"""

    def __init__(self):
        self.retriever = get_counselor_retriever()
        self.llm = get_llm()

    # ==================== 检索与模式判定 ====================

    def _retrieve(self, question: str, security_level: Optional[int] = None) -> List[Dict]:
        try:
            return self.retriever.search(
                question, top_k=settings.COUNSELOR_TOP_K,
                security_level=security_level,
            )
        except Exception:
            logger.warning("导员知识库检索异常:\n%s", traceback.format_exc())
            return []

    @staticmethod
    def _is_hit(chunks: List[Dict]) -> bool:
        """
        判断是否命中知识库。

        优先使用条款的"绝对余弦相似度"（无天花板效应）；
        若向量索引不可用，则退化为关键词命中（BM25 归一化分足够高）。
        """
        if not chunks:
            return False
        cosines = [c.get("cosine") for c in chunks if c.get("cosine") is not None]
        if cosines:
            return max(cosines) >= settings.COUNSELOR_MIN_SCORE
        return any((c.get("bm25_norm") or 0) > 0.5 for c in chunks)

    @staticmethod
    def _build_sources(chunks: List[Dict]) -> List[Dict]:
        return [
            {
                "source_title": c.get("source_title", ""),
                "article_no": c.get("article_no", ""),
                "chapter": c.get("chapter", ""),
                "source_url": c.get("source_url", ""),
                "snippet": (c.get("content", "") or "")[:160],
                "score": round(float(c.get("score", 0)), 4),
            }
            for c in chunks
        ]

    # ==================== 同步问答 ====================

    def ask(
        self, question: str, chat_history: Optional[List[Dict]] = None,
        security_level: Optional[int] = None,
    ) -> Dict:
        """同步问答（人设 + 知识库双模式）"""
        t_start = time.time()

        if is_counselor_greeting(question):
            return {
                "answer": get_counselor_greeting(),
                "sources": [],
                "mode": "persona",
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                "latency": {"retrieval_ms": 0, "llm_ms": 0, "total_ms": 0},
            }

        t_ret_start = time.time()
        chunks = self._retrieve(question, security_level=security_level)
        hit = self._is_hit(chunks)
        context = chunks if hit else []
        t_retrieval = (time.time() - t_ret_start) * 1000

        messages = build_counselor_messages(question, context, chat_history)
        t_llm_start = time.time()
        try:
            result = self.llm.chat(messages)
        except LLMException:
            raise
        t_llm = (time.time() - t_llm_start) * 1000

        return {
            "answer": result["content"],
            "sources": self._build_sources(context),
            "mode": "knowledge" if hit else "persona",
            "usage": result.get("usage", {}),
            "latency": {
                "retrieval_ms": round(t_retrieval),
                "llm_ms": round(t_llm),
                "total_ms": round((time.time() - t_start) * 1000),
            },
        }

    # ==================== 流式问答 ====================

    async def ask_stream(
        self, question: str, chat_history: Optional[List[Dict]] = None,
        security_level: Optional[int] = None,
    ) -> AsyncGenerator[Dict, None]:
        """
        流式问答（SSE）

        Yields:
            {"type": "token", "data": str}
            {"type": "sources", "data": list}
            {"type": "done", "data": dict}
            {"type": "error", "data": str}
        """
        t_start = time.time()

        # 问候语短路
        if is_counselor_greeting(question):
            greeting = get_counselor_greeting()
            yield {"type": "token", "data": greeting}
            yield {"type": "sources", "data": []}
            yield {"type": "done", "data": {
                "full_answer": greeting, "mode": "persona", "sources": [],
                "latency": {"retrieval_ms": 0, "llm_ms": 0, "total_ms": 0},
            }}
            return

        # 检索 + 模式判定
        t_ret_start = time.time()
        chunks = self._retrieve(question, security_level=security_level)
        hit = self._is_hit(chunks)
        context = chunks if hit else []
        t_retrieval = (time.time() - t_ret_start) * 1000

        sources = self._build_sources(context)
        mode = "knowledge" if hit else "persona"
        messages = build_counselor_messages(question, context, chat_history)

        # 流式生成
        t_llm_start = time.time()
        full_answer = ""
        try:
            async for token in self.llm.chat_stream(messages):
                full_answer += token
                yield {"type": "token", "data": token}
        except LLMException as e:
            yield {"type": "error", "data": f"导员服务调用失败: {str(e)}"}
            return
        t_llm = (time.time() - t_llm_start) * 1000

        yield {"type": "sources", "data": sources}
        yield {"type": "done", "data": {
            "full_answer": full_answer,
            "mode": mode,
            "sources": sources,
            "latency": {
                "retrieval_ms": round(t_retrieval),
                "llm_ms": round(t_llm),
                "total_ms": round((time.time() - t_start) * 1000),
            },
        }}

    # ==================== 日志归档 ====================

    @staticmethod
    def save_log(
        question: str,
        answer: str,
        session_id: str,
        user_id: int,
        mode: str,
        sources: list,
        latency: dict,
    ) -> None:
        """保存导员问答日志（独立归档，失败不影响主流程）"""
        db = SessionLocal()
        try:
            log = CounselorLog(
                session_id=session_id,
                user_id=user_id,
                question=question,
                answer=answer,
                mode=mode,
                source_titles=[s.get("source_title", "") for s in sources],
                is_answered=1 if mode == "knowledge" else 0,
                retrieval_ms=latency.get("retrieval_ms", 0),
                llm_ms=latency.get("llm_ms", 0),
                total_ms=latency.get("total_ms", 0),
            )
            db.add(log)
            db.commit()
        except Exception:
            db.rollback()
            logger.warning("保存导员问答日志失败:\n%s", traceback.format_exc())
        finally:
            db.close()


# --- 全局单例 ---
_counselor_service: Optional[CounselorService] = None


def get_counselor_service() -> CounselorService:
    """获取导员服务单例"""
    global _counselor_service
    if _counselor_service is None:
        _counselor_service = CounselorService()
    return _counselor_service
