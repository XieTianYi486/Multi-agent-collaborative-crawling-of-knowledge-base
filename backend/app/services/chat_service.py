# ============================================================
# 聊天服务层 —— RAG 问答核心编排
# 流程：查询处理 → 混合检索 → 重排序 → Prompt组装 → LLM生成
# ============================================================

import json
import logging
import time
import traceback
import uuid as uuid_lib
from typing import AsyncGenerator, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import LLMException, RetrievalException
from app.models.chat import ChatSession, ChatMessage, ChatLog
from app.models.document import Category, Document
from app.rag.retrievers.hybrid_retriever import get_hybrid_retriever
from app.rag.llm.dashscope_llm import get_llm
from app.rag.reranker.llm_reranker import get_reranker
from app.rag.prompts.chat_prompt import build_chat_messages
from app.rag.query_processor.intent_recognition import (
    detect_intent, get_greeting_response, get_rejected_response,
)
from app.rag.query_processor.query_rewrite import get_query_rewriter
from app.db.cache import cache
from app.db.sqlite import SessionLocal

logger = logging.getLogger(__name__)

# 无检索候选时的统一拒答文案。
# 注意：文案必须包含 save_chat_log 的 refusal_patterns 中至少一个子串，
# 否则问答日志的 is_answered 判定失真（统计页"已解答率"错误）。
# 由 tests/test_refusal_consistency.py 提供回归保护。
REFUSAL_FALLBACK_ANSWER = (
    "抱歉，知识库中未找到与您问题相关的资料。"
    "建议您换个问法再试，或等待爬取流水线收录更多内容后再次查询。"
)


class ChatService:
    """问答服务（编排完整 RAG 流程）"""

    def __init__(self):
        self.hybrid = get_hybrid_retriever()
        self.llm = get_llm()
        self.reranker = get_reranker()

    # ==================== 问答缓存 ====================

    @staticmethod
    def _scope_signature(
        category_ids: Optional[List[int]] = None,
        document_ids: Optional[List[int]] = None,
    ) -> str:
        """
        生成检索范围的稳定签名。

        缓存键必须区分检索范围，否则「限定分类 A」的结果会被
        「不限范围」或「限定分类 B」的相同问题复用，导致答案串味。
        """
        c = ",".join(str(x) for x in sorted(category_ids)) if category_ids else ""
        d = ",".join(str(x) for x in sorted(document_ids)) if document_ids else ""
        return f"c[{c}]d[{d}]"

    @staticmethod
    def _get_cached_answer(
        question: str, security_level: int, scope_sig: str = ""
    ) -> Optional[Dict]:
        """读取单轮问答缓存（命中返回 {answer, sources}，未命中返回 None）"""
        key = cache.make_key(question, security_level, scope_sig, prefix="qa")
        cached = cache.get_from_memory(key)
        if cached is None:
            cached = cache.get_from_disk(key)
        return cached

    @staticmethod
    def _store_cached_answer(
        question: str, security_level: int, answer: str, sources: list,
        scope_sig: str = "",
    ) -> None:
        """写入单轮问答缓存（内存 + 磁盘，TTL 取配置 CACHE_TTL_ANSWER）"""
        key = cache.make_key(question, security_level, scope_sig, prefix="qa")
        payload = {"answer": answer, "sources": sources}
        cache.set_to_memory(key, payload)
        cache.set_to_disk(key, payload, ttl=settings.CACHE_TTL_ANSWER)

    # ==================== 非流式问答 ====================

    def ask(
        self,
        question: str,
        security_level: int = 1,
        category_ids: Optional[List[int]] = None,
        document_ids: Optional[List[int]] = None,
        chat_history: Optional[List[Dict]] = None,
    ) -> Dict:
        """
        同步问答（非流式）

        返回: {
            "answer": str, "sources": list, "usage": dict, "latency": dict
        }
        """
        t_start = time.time()
        scope_sig = self._scope_signature(category_ids, document_ids)

        # === 第0步：意图识别 ===
        intent = detect_intent(question)
        if intent == "greeting":
            return self._fast_response(get_greeting_response(question))
        if intent == "rejected":
            return self._fast_response(get_rejected_response())

        # === 第0.25步：问答缓存（仅单轮对话；多轮历史影响答案，不缓存）===
        cache_key = None
        if not chat_history:
            cached = self._get_cached_answer(question, security_level, scope_sig)
            if cached:
                return {
                    "answer": cached["answer"],
                    "sources": cached.get("sources", []),
                    "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                    "latency": {
                        "retrieval_ms": 0, "rerank_ms": 0, "llm_ms": 0,
                        "total_ms": round((time.time() - t_start) * 1000),
                        "cache_hit": True,
                    },
                }
            cache_key = cache.make_key(question, security_level, scope_sig, prefix="qa")

        # === 第0.5步：查询改写 ===
        query_rewriter = get_query_rewriter()
        rewrite_result = query_rewriter.rewrite(question, chat_history)
        search_query = rewrite_result["rewritten"]

        # === 第1步：混合检索（主查询 + 改写变体多查询增强）===
        # 单个变体检索失败时降级跳过，仅当全部查询失败才视为检索失败
        t_retrieval_start = time.time()
        queries = [search_query]
        for v in rewrite_result.get("variants", [])[:2]:
            if v and v != search_query:
                queries.append(v)
        try:
            candidates, query_errors = self._multi_query_search(
                queries, security_level, settings.FUSION_TOP_K
            )
            if not candidates and query_errors:
                raise RetrievalException("知识库检索失败: " + "; ".join(query_errors))
        except RetrievalException:
            raise
        except Exception as e:
            raise RetrievalException(f"知识库检索失败: {str(e)}")
        t_retrieval = (time.time() - t_retrieval_start) * 1000

        # === 第1.5步：发布/密级二次过滤（仅允许已通过审核且密级内的文档）===
        visible_ids = self._visible_doc_ids(security_level, category_ids, document_ids)
        candidates = [c for c in candidates if c.get("document_id") in visible_ids]

        # === 第2步：拒答兜底（无任何检索结果时才短路，其余交给重排+LLM 判断）===
        # 注：融合分数经过相对归一化，不适合作为绝对阈值，
        # 误拒"有答案却检索不到"的回归问题即源于此。
        if not candidates:
            return {
                "answer": REFUSAL_FALLBACK_ANSWER,
                "sources": [],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                "latency": {
                    "retrieval_ms": round(t_retrieval),
                    "rerank_ms": 0,
                    "llm_ms": 0,
                    "total_ms": round((time.time() - t_start) * 1000),
                },
            }

        # === 第3步：LLM 重排序（候选 -> 最相关 Top-N）===
        t_rerank_start = time.time()
        rerank_candidates = candidates[:settings.RERANK_CANDIDATES]
        top_chunks = self.reranker.rerank(question, rerank_candidates)
        top_chunks = top_chunks[:settings.RERANK_TOP_N]
        t_rerank = (time.time() - t_rerank_start) * 1000

        # === 第4步：组装 Prompt ===
        messages = build_chat_messages(
            question=question,
            context_chunks=top_chunks,
            chat_history=chat_history,
        )

        # === 第5步：LLM 生成 ===
        t_llm_start = time.time()
        try:
            result = self.llm.chat(messages)
        except LLMException as e:
            raise e
        t_llm = (time.time() - t_llm_start) * 1000

        # === 构建来源信息 ===
        sources = []
        for c in top_chunks:
            sources.append({
                "document_id": c.get("document_id", 0),
                "document_name": c.get("document_name", ""),
                "chapter": c.get("chapter", ""),
                "page": c.get("page", 1),
                "snippet": c.get("content", "")[:200],
                "score": round(c.get("score", 0), 4),
                "source_url": c.get("source_url", ""),
            })

        # === 总耗时 ===
        total_ms = round((time.time() - t_start) * 1000)

        # 写入单轮问答缓存（供后续相同问题直接命中）
        if cache_key:
            self._store_cached_answer(
                question, security_level, result["content"], sources, scope_sig
            )

        return {
            "answer": result["content"],
            "sources": sources,
            "usage": result.get("usage", {}),
            "latency": {
                "retrieval_ms": round(t_retrieval),
                "rerank_ms": round(t_rerank),
                "llm_ms": round(t_llm),
                "total_ms": total_ms,
            },
        }

    # ==================== 流式问答 ====================

    async def ask_stream(
        self,
        question: str,
        security_level: int = 1,
        category_ids: Optional[List[int]] = None,
        document_ids: Optional[List[int]] = None,
        chat_history: Optional[List[Dict]] = None,
    ) -> AsyncGenerator[Dict, None]:
        """
        流式问答（SSE）

        Yields:
            {"type": "token", "data": str} |
            {"type": "sources", "data": list} |
            {"type": "done", "data": dict} |
            {"type": "error", "data": str}
        """
        t_start = time.time()
        scope_sig = self._scope_signature(category_ids, document_ids)

        # === 第0步：意图识别 ===
        intent = detect_intent(question)
        if intent == "greeting":
            yield {"type": "token", "data": get_greeting_response(question)}
            yield {"type": "sources", "data": []}
            yield {"type": "done", "data": {
                "full_answer": get_greeting_response(question),
                "total_tokens": 0,
                "latency": {"retrieval_ms": 0, "llm_ms": 0, "total_ms": 0},
            }}
            return
        if intent == "rejected":
            yield {"type": "token", "data": get_rejected_response()}
            yield {"type": "sources", "data": []}
            yield {"type": "done", "data": {
                "full_answer": get_rejected_response(),
                "total_tokens": 0,
                "latency": {"retrieval_ms": 0, "llm_ms": 0, "total_ms": 0},
            }}
            return

        # === 第0.25步：问答缓存（仅单轮对话；多轮历史影响答案，不缓存）===
        cache_key = None
        if not chat_history:
            cached = self._get_cached_answer(question, security_level, scope_sig)
            if cached:
                yield {"type": "token", "data": cached["answer"]}
                yield {"type": "sources", "data": cached.get("sources", [])}
                yield {"type": "done", "data": {
                    "full_answer": cached["answer"],
                    "total_tokens": len(cached["answer"]) // 3,  # 粗略估算
                    "status": "cache_hit",
                    "latency": {
                        "retrieval_ms": 0, "llm_ms": 0,
                        "total_ms": round((time.time() - t_start) * 1000),
                    },
                }}
                return
            cache_key = cache.make_key(question, security_level, scope_sig, prefix="qa")

        # === 第0.5步：查询改写 ===
        query_rewriter = get_query_rewriter()
        rewrite_result = query_rewriter.rewrite(question, chat_history)
        search_query = rewrite_result["rewritten"]

        # === 第1步：混合检索（主查询 + 改写变体多查询增强）===
        t_retrieval_start = time.time()
        queries = [search_query]
        for v in rewrite_result.get("variants", [])[:2]:
            if v and v != search_query:
                queries.append(v)
        try:
            candidates, query_errors = self._multi_query_search(
                queries, security_level, settings.FUSION_TOP_K
            )
            if not candidates and query_errors:
                raise RetrievalException("知识库检索失败: " + "; ".join(query_errors))
        except Exception as e:
            yield {"type": "error", "data": f"检索失败: {str(e)}"}
            return
        t_retrieval = (time.time() - t_retrieval_start) * 1000

        # === 第1.5步：发布/密级二次过滤 ===
        visible_ids = self._visible_doc_ids(security_level, category_ids, document_ids)
        candidates = [c for c in candidates if c.get("document_id") in visible_ids]

        # === 第2步：拒答兜底（无任何检索结果时才短路）===
        if not candidates:
            total_ms = round((time.time() - t_start) * 1000)
            yield {
                "type": "done",
                "data": {
                    "answer": REFUSAL_FALLBACK_ANSWER,
                    "sources": [],
                    "status": "not_found",
                    "latency": {
                        "retrieval_ms": round(t_retrieval), "llm_ms": 0,
                        "total_ms": total_ms,
                    },
                }
            }
            return

        # === 第3步：LLM 重排序 ===
        rerank_candidates = candidates[:settings.RERANK_CANDIDATES]
        top_chunks = self.reranker.rerank(question, rerank_candidates)
        top_chunks = top_chunks[:settings.RERANK_TOP_N]
        sources = [
            {
                "document_id": c.get("document_id", 0),
                "document_name": c.get("document_name", ""),
                "chapter": c.get("chapter", ""),
                "page": c.get("page", 1),
                "snippet": c.get("content", "")[:200],
                "score": round(c.get("score", 0), 4),
                "source_url": c.get("source_url", ""),
            }
            for c in top_chunks
        ]

        # === 第4步：组装 Prompt ===
        messages = build_chat_messages(
            question=question,
            context_chunks=top_chunks,
            chat_history=chat_history,
        )

        # === 第5步：流式 LLM 生成 ===
        t_llm_start = time.time()
        full_answer = ""
        try:
            async for token in self.llm.chat_stream(messages):
                full_answer += token
                yield {"type": "token", "data": token}
        except LLMException as e:
            yield {"type": "error", "data": f"AI 服务调用失败: {str(e)}"}
            return
        t_llm = (time.time() - t_llm_start) * 1000

        # 写入单轮问答缓存（供后续相同问题直接命中）
        if cache_key:
            self._store_cached_answer(question, security_level, full_answer, sources, scope_sig)

        # === 发送来源 ===
        yield {"type": "sources", "data": sources}

        # === 完成 ===
        total_ms = round((time.time() - t_start) * 1000)
        yield {
            "type": "done",
            "data": {
                "full_answer": full_answer,
                "total_tokens": len(full_answer) // 3,  # 粗略估算
                "latency": {
                    "retrieval_ms": round(t_retrieval),
                    "llm_ms": round(t_llm),
                    "total_ms": total_ms,
                },
            }
        }

    # ==================== 纯检索（不调用 LLM） ====================

    def search_chunks(
        self,
        query: str,
        security_level: int = 1,
        top_k: int = 10,
        category_ids: Optional[List[int]] = None,
        document_ids: Optional[List[int]] = None,
    ) -> List[Dict]:
        """
        混合检索并返回经发布/密级过滤的知识片段，不调用 LLM。

        供开放 API 的检索接口使用：调用方拿到片段后自行组装上下文。

        参数:
            query: 检索语句
            security_level: 可访问密级上限
            top_k: 返回片段数
            category_ids: 限定分类范围（可选，含所选分类的子孙分类）
            document_ids: 限定文档范围（可选）

        返回:
            按融合分数降序的片段列表
        """
        chunks = self.hybrid.search(
            query=query, top_k=top_k, security_level=security_level,
        )
        visible = self._visible_doc_ids(security_level, category_ids, document_ids)
        return [c for c in chunks if c.get("document_id") in visible]

    # ==================== 辅助方法 ====================

    @staticmethod
    def _expand_category_ids(db: Session, category_ids: List[int]) -> set:
        """
        将所选分类展开为「自身 + 所有子孙分类」的 ID 集合。

        分类树通过 Category.parent_id 自引用，采用逐层 BFS 展开，
        不依赖 SQLite 递归 CTE（低版本不支持），保证与分类树展示一致。
        """
        rows = db.query(Category.id, Category.parent_id).all()
        children_map: Dict[int, List[int]] = {}
        for cid, pid in rows:
            children_map.setdefault(pid, []).append(cid)

        expanded: set = set()
        queue = list(category_ids)
        while queue:
            cid = queue.pop()
            if cid in expanded:
                continue
            expanded.add(cid)
            queue.extend(children_map.get(cid, []))
        return expanded

    @staticmethod
    def _visible_doc_ids(
        security_level: int,
        category_ids: Optional[List[int]] = None,
        document_ids: Optional[List[int]] = None,
    ) -> set:
        """
        获取当前用户可检索的文档 ID 集合。

        严格遵循企业发布流与密级控制：
        - 仅"已发布(status=1) + 已通过审核(review_status=2)"的文档可被检索
        - 且密级不得高于用户可访问的安全级别

        可选叠加检索范围限定（问答/检索接口传入）：
        - category_ids: 只保留所选分类及其子孙分类下的文档
        - document_ids: 只保留指定文档

        用于对检索召回结果做二次过滤，防止未审核/越权内容被问答引用。
        """
        db = SessionLocal()
        try:
            query = db.query(Document.id).filter(
                Document.status == 1,
                Document.review_status == 2,
                Document.security_level <= security_level,
            )
            if category_ids:
                scope_cats = ChatService._expand_category_ids(db, category_ids)
                query = query.filter(Document.category_id.in_(scope_cats))
            if document_ids:
                query = query.filter(Document.id.in_(document_ids))
            return {r[0] for r in query.all()}
        finally:
            db.close()

    @staticmethod
    def _fast_response(answer: str) -> Dict:
        """构建快速响应（不走 RAG 流程）"""
        return {
            "answer": answer,
            "sources": [],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            "latency": {
                "retrieval_ms": 0, "rerank_ms": 0,
                "llm_ms": 0, "total_ms": 0,
            },
        }

    # ==================== 多查询检索 ====================

    def _multi_query_search(
        self,
        queries: List[str],
        security_level: int,
        top_k: int,
    ) -> Tuple[List[Dict], List[str]]:
        """
        对主查询及其改写变体分别执行混合检索，按 chunk_id 合并去重（保留最高分）。

        单个查询失败时降级跳过并记录错误，仅当全部查询失败时调用方才会判定检索失败。

        返回: (合并后的候选列表（按分数降序）, 各查询的错误信息列表)
        """
        merged: Dict[str, Dict] = {}
        errors: List[str] = []
        for q in queries:
            try:
                results = self.hybrid.search(
                    query=q, top_k=top_k, security_level=security_level,
                )
            except Exception as e:
                errors.append(str(e))
                logger.warning(f"多查询检索变体失败: {e}")
                continue
            for c in results:
                cid = c.get("chunk_id", "")
                if not cid:
                    continue
                if cid not in merged or c.get("score", 0) > merged[cid].get("score", 0):
                    merged[cid] = c
        merged_list = sorted(
            merged.values(), key=lambda x: x.get("score", 0), reverse=True
        )
        return merged_list, errors

    # ==================== 会话管理 ====================

    @staticmethod
    def save_chat_log(
        question: str,
        answer: str,
        session_id: str,
        user_id: int,
        sources: list,
        latency: dict,
        usage: dict,
    ) -> None:
        """保存问答日志到数据库（使用独立会话，失败不影响主流程）"""
        db = SessionLocal()
        try:
            # 综合判断是否真正命中：有来源 + LLM 未拒绝
            has_sources = bool(sources)
            refusal_patterns = [
                "未找到相关信息", "未找到关于", "知识库中未找到", "无法回答",
                "建议您咨询", "无法获取", "参考资料中未涉及", "未涉及",
                "未找到与您问题相关的信息",
            ]
            is_refusal = any(p in answer for p in refusal_patterns)
            is_answered = 1 if (has_sources and not is_refusal) else 0
            log = ChatLog(
                session_id=session_id,
                user_id=user_id,
                question=question,
                answer=answer,
                source_doc_ids=[s.get("document_id") for s in sources],
                is_answered=is_answered,
                retrieval_ms=latency.get("retrieval_ms", 0),
                rerank_ms=latency.get("rerank_ms", 0),
                llm_ms=latency.get("llm_ms", 0),
                total_ms=latency.get("total_ms", 0),
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
            )
            db.add(log)
            db.commit()
        except Exception:
            db.rollback()
            logger.warning(f"保存问答日志失败: {traceback.format_exc()}")
        finally:
            db.close()


# --- 全局单例 ---
_chat_service: Optional[ChatService] = None


def get_chat_service() -> ChatService:
    """获取聊天服务单例"""
    global _chat_service
    if _chat_service is None:
        _chat_service = ChatService()
    return _chat_service
