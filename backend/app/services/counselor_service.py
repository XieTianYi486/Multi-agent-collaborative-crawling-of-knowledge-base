# ============================================================
# AI 助手 服务层
#
# 两层能力：
#   1. 任务型 Agent：任务/个人数据/找资料类问题走工具链路（可查可办）；
#   2. 主 RAG 链路：普通概念问答仍复用 ChatService 的混合检索。
#
# 任何 Agent 异常都会自动回退到 RAG，保证助手不会因为工具故障而不可用。
# ============================================================

import logging
import traceback
from typing import AsyncGenerator, Dict, List, Optional

from app.agent.agent import get_assistant_agent
from app.agent.registry import ToolContext
from app.agent.routing import should_use_tools
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

    @staticmethod
    def _build_ctx(
        user_id: Optional[int],
        username: str,
        role_code: str,
        security_level: int,
        session_id: Optional[str],
    ) -> Optional[ToolContext]:
        if user_id is None or not role_code:
            return None
        return ToolContext(
            user_id=user_id,
            username=username or "用户",
            role_code=role_code,
            security_level=security_level,
            session_id=session_id,
        )

    def ask(
        self,
        question: str,
        chat_history: Optional[List[Dict]] = None,
        security_level: Optional[int] = None,
        user_profile: Optional[Dict] = None,
        memory: Optional[List[Dict]] = None,
        user_id: Optional[int] = None,
        username: str = "",
        role_code: str = "",
        session_id: Optional[str] = None,
    ) -> Dict:
        """同步问答：任务型问题走工具 Agent，其余走主 RAG"""
        level = security_level if security_level is not None else 1
        ctx = self._build_ctx(user_id, username, role_code, level, session_id)

        if ctx is not None:
            try:
                agent = get_assistant_agent()
                if should_use_tools(question, ctx.role_code):
                    result = agent.run_sync(question, ctx, chat_history)
                    if result is not None:
                        return result
            except Exception:
                # 工具链路失败不能影响问答主流程，直接降级到 RAG
                logger.warning("AI 助手工具链路失败，降级 RAG:\n%s", traceback.format_exc())

        result = self.chat.ask(
            question=question,
            security_level=level,
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
        user_id: Optional[int] = None,
        username: str = "",
        role_code: str = "",
        session_id: Optional[str] = None,
    ) -> AsyncGenerator[Dict, None]:
        """
        流式问答：
        - 任务型问题：先推工具步骤，再推最终回答/确认卡片；
        - 普通问题：直通主 RAG，行为与之前一致。
        """
        level = security_level if security_level is not None else 1
        ctx = self._build_ctx(user_id, username, role_code, level, session_id)

        if ctx is not None:
            handled = False
            try:
                agent = get_assistant_agent()
                if should_use_tools(question, ctx.role_code):
                    async for event in agent.run_stream(question, ctx, chat_history):
                        handled = True
                        yield event
            except Exception:
                logger.warning("AI 助手工具链路失败:\n%s", traceback.format_exc())
                if handled:
                    yield {"type": "error", "data": "助手执行工具时出错，请稍后重试"}
                    return
                # 尚未产生任何事件，允许降级到 RAG
            if handled:
                return

        sources: List[Dict] = []
        async for event in self.chat.ask_stream(
            question=question,
            security_level=level,
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
