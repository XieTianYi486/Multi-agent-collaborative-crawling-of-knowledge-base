# ============================================================
# AI 导员 服务层 —— 人设陪伴 + 导员知识库作答 双模式编排
#
# 知识注入有两种模式（settings.COUNSELOR_CONTEXT_MODE）：
#   full      全量注入：把整库条款一次性放进 system prompt，由模型自行判断是否涵盖
#             问题（类似 CLAUDE.md 的记忆模式）。适用于条款量小的知识库，
#             无漏召回、无阈值调参。
#   retrieval 检索模式：向量+BM25 混合检索 top-k + 绝对余弦阈值判定命中。
#             条款量变大后使用。
#
# 关键设计（"不编造校规"的机制保障）：
#   1. 先准备"导员知识库"上下文（独立索引，不碰教学知识库）
#   2. 有可用条款（全量恒有 / 检索命中）→ 知识模式：条款作为【导员知识库】交给 LLM 严格作答
#   3. 无可用条款 → 陪伴模式：不做事务性断言，只做共情引导，并提示线下核实
#   两条路径都注入"温柔有耐心"的人设，且系统提示中明令禁止编造具体校规
#
# 全量注入模式下没有"检索命中"这一步，改用"回答里是否引用了具体条款"
# 来判定 mode 与 sources（既保留前端出处展示，又避免把无关内容当成命中）。
# ============================================================

import logging
import re
import time
import traceback
from typing import AsyncGenerator, Dict, List, Optional, Tuple

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
    def _is_full_mode() -> bool:
        return (settings.COUNSELOR_CONTEXT_MODE or "").strip().lower() == "full"

    def _prepare_context(
        self, question: str, security_level: Optional[int] = None,
    ) -> Tuple[List[Dict], bool]:
        """
        准备交给 LLM 的知识库上下文。

        返回 (context_chunks, full_injected)：
        - 全量注入模式：返回整库条款（按密级过滤），full_injected=True
          （无条款时仍为 True，交回上层按空上下文处理，走陪伴模式）
        - 检索模式：命中才返回 top-k 条款，否则返回空列表
        """
        if self._is_full_mode():
            try:
                chunks = self.retriever.all_chunks()
                if security_level is not None:
                    chunks = [
                        c for c in chunks
                        if (c.get("security_level", 1) or 1) <= security_level
                    ]
                return chunks, True
            except Exception:
                logger.warning("导员知识库全量加载异常:\n%s", traceback.format_exc())
                return [], True

        chunks = self._retrieve(question, security_level=security_level)
        return (chunks if self._is_hit(chunks) else []), False

    @staticmethod
    def _is_hit(chunks: List[Dict]) -> bool:
        """
        判断是否命中知识库（仅检索模式使用）。

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
                "score": round(float(c.get("score") or 0), 4),
            }
            for c in chunks
        ]

    @staticmethod
    def _title_variants(title: str) -> List[str]:
        """条款出处的可匹配标题写法（含去掉年份括号的简称）"""
        t = (title or "").strip()
        if not t:
            return []
        variants = [t]
        core = re.split(r"[（(]", t, 1)[0].strip()
        if core and core != t:
            variants.append(core)
        return variants

    @classmethod
    def _cited_sources(cls, answer: str, chunks: List[Dict]) -> List[Dict]:
        """
        全量注入模式下的出处回标：从回答里找出被引用的条款（标题 + 条号都对上）。
        """
        if not answer:
            return []
        cited = []
        for c in chunks:
            variants = cls._title_variants(c.get("source_title", ""))
            if not variants or not any(v in answer for v in variants):
                continue
            article_no = c.get("article_no") or ""
            if article_no and article_no not in answer:
                continue
            cited.append(c)
        return cls._build_sources(cited)

    def _resolve_sources_and_mode(
        self, answer: str, context: List[Dict], full: bool,
    ) -> Tuple[List[Dict], str]:
        """按注入模式决定 sources 与 mode（knowledge / persona）"""
        if full:
            sources = self._cited_sources(answer, context)
            return sources, ("knowledge" if sources else "persona")
        return self._build_sources(context), ("knowledge" if context else "persona")

    # ==================== 同步问答 ====================

    def ask(
        self,
        question: str,
        chat_history: Optional[List[Dict]] = None,
        security_level: Optional[int] = None,
        user_profile: Optional[Dict] = None,
        memory: Optional[List[Dict]] = None,
    ) -> Dict:
        """
        同步问答（人设 + 知识库双模式）

        security_level: 密级过滤（None 表示不过滤，管理员场景）
        user_profile: 登录用户身份 {"name": ..., "department": ...}，让导员知道在和谁说话
        memory: 跨会话历史要点 [{"question","answer","date"}]，让导员记得既往聊过的事
        """
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
        context, full = self._prepare_context(question, security_level=security_level)
        t_retrieval = (time.time() - t_ret_start) * 1000

        messages = build_counselor_messages(
            question, context, chat_history, full=full,
            user_profile=user_profile, memory=memory,
        )
        t_llm_start = time.time()
        try:
            result = self.llm.chat(messages)
        except LLMException:
            raise
        t_llm = (time.time() - t_llm_start) * 1000

        sources, mode = self._resolve_sources_and_mode(result["content"], context, full)

        return {
            "answer": result["content"],
            "sources": sources,
            "mode": mode,
            "usage": result.get("usage", {}),
            "latency": {
                "retrieval_ms": round(t_retrieval),
                "llm_ms": round(t_llm),
                "total_ms": round((time.time() - t_start) * 1000),
            },
        }

    # ==================== 流式问答 ====================

    async def ask_stream(
        self,
        question: str,
        chat_history: Optional[List[Dict]] = None,
        security_level: Optional[int] = None,
        user_profile: Optional[Dict] = None,
        memory: Optional[List[Dict]] = None,
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

        # 准备上下文 + 模式判定
        t_ret_start = time.time()
        context, full = self._prepare_context(question, security_level=security_level)
        t_retrieval = (time.time() - t_ret_start) * 1000

        messages = build_counselor_messages(
            question, context, chat_history, full=full,
            user_profile=user_profile, memory=memory,
        )

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

        # 生成完毕才能确定真正引用了哪些条款（全量注入模式下）
        sources, mode = self._resolve_sources_and_mode(full_answer, context, full)

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
