# ============================================================
# AI 助手 服务层
#
# 悬浮 AI 助手直接复用主问答 RAG 链路（教学知识库），不再维护独立知识库：
#   - ask / ask_stream 透传给 ChatService（嵌入式开发教学资料检索）
#   - save_log 继续归档到 counselor_logs，前端会话/日志表结构保持不变
# ============================================================

import logging
import traceback
from typing import AsyncGenerator, Dict, List, Optional

from app.db.sqlite import SessionLocal
from app.models.counselor import CounselorLog
from app.services.chat_service import get_chat_service

logger = logging.getLogger(__name__)


class CounselorService:
    """AI 助手服务（复用主教学知识库 RAG）"""

    def __init__(self):
        self.chat = get_chat_service()

    @staticmethod
    def _mode(sources: List[Dict]) -> str:
        """有引用来源视为知识库作答，否则为通用回答（前端据此显示标签）"""
        return "knowledge" if sources else "general"

    def ask(
        self,
        question: str,
        chat_history: Optional[List[Dict]] = None,
        security_level: Optional[int] = None,
        user_profile: Optional[Dict] = None,
        memory: Optional[List[Dict]] = None,
    ) -> Dict:
        """同步问答：主 RAG 链路（user_profile/memory 保留参数以兼容旧调用）"""
        result = self.chat.ask(
            question=question,
            security_level=security_level if security_level is not None else 1,
            chat_history=chat_history,
        )
        result["mode"] = self._mode(result.get("sources", []))
        return result

    async def ask_stream(
        self,
        question: str,
        chat_history: Optional[List[Dict]] = None,
        security_level: Optional[int] = None,
        user_profile: Optional[Dict] = None,
        memory: Optional[List[Dict]] = None,
    ) -> AsyncGenerator[Dict, None]:
        """流式问答：直接透传主 RAG 链路事件，并在结束时补充 mode"""
        sources: List[Dict] = []
        async for event in self.chat.ask_stream(
            question=question,
            security_level=security_level if security_level is not None else 1,
            chat_history=chat_history,
        ):
            if event["type"] == "sources":
                sources = event.get("data") or []
            elif event["type"] == "done":
                event["data"]["mode"] = self._mode(
                    event["data"].get("sources") or sources
                )
            yield event

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
        """保存 AI 助手问答日志（独立归档，失败不影响主流程）"""
        db = SessionLocal()
        try:
            log = CounselorLog(
                session_id=session_id,
                user_id=user_id,
                question=question,
                answer=answer,
                mode=mode,
                source_titles=[
                    s.get("source_title") or s.get("title") or s.get("document_name", "")
                    for s in sources
                ],
                is_answered=1 if mode == "knowledge" else 0,
                retrieval_ms=latency.get("retrieval_ms", 0),
                llm_ms=latency.get("llm_ms", 0),
                total_ms=latency.get("total_ms", 0),
            )
            db.add(log)
            db.commit()
        except Exception:
            db.rollback()
            logger.warning("保存 AI 助手问答日志失败:\n%s", traceback.format_exc())
        finally:
            db.close()


# --- 全局单例 ---
_counselor_service: Optional[CounselorService] = None


def get_counselor_service() -> CounselorService:
    """获取 AI 助手服务单例"""
    global _counselor_service
    if _counselor_service is None:
        _counselor_service = CounselorService()
    return _counselor_service
