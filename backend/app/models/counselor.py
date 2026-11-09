# ============================================================
# SQLAlchemy 数据模型 - AI 助手
# 悬浮 AI 助手复用主教学知识库 RAG，但会话/消息/日志独立存放，
# 与教学问答的 chat_sessions 隔离，便于分别统计与清理
# ============================================================

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column, Integer, String, Text, DateTime, JSON, ForeignKey
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.sqlite import Base
from app.models.user import utcnow


class CounselorSession(Base):
    """
    AI 助手会话表
    一个用户可以有多段与 AI 助手的对话，独立于教学问答的 chat_sessions
    """
    __tablename__ = "counselor_sessions"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, comment="会话ID（UUID 前缀）"
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True, comment="用户ID"
    )
    title: Mapped[str] = mapped_column(
        String(255), default="与 AI 助手的新对话", comment="会话标题"
    )
    message_count: Mapped[int] = mapped_column(
        Integer, default=0, comment="消息数量"
    )
    last_message_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, comment="最后消息时间"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )

    messages: Mapped[list["CounselorMessage"]] = relationship(
        "CounselorMessage", back_populates="session",
        cascade="all, delete-orphan", order_by="CounselorMessage.created_at"
    )

    def __repr__(self):
        return f"<CounselorSession(id='{self.id}', title='{self.title}')>"


class CounselorMessage(Base):
    """
    AI 助手消息表
    记录每轮与 AI 助手的问答，mode 区分"知识库依据"与"通用回答"两条路径
    """
    __tablename__ = "counselor_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("counselor_sessions.id", ondelete="CASCADE"),
        nullable=False, index=True, comment="会话ID"
    )
    role: Mapped[str] = mapped_column(
        String(16), nullable=False, comment="角色：user / assistant"
    )
    content: Mapped[str] = mapped_column(
        Text, nullable=False, comment="消息内容"
    )
    mode: Mapped[Optional[str]] = mapped_column(
        String(16), nullable=True,
        comment="回答模式：knowledge=基于知识库作答, general=通用回答"
    )
    sources: Mapped[Optional[list]] = mapped_column(
        JSON, nullable=True, comment="引用的知识库来源（JSON 数组）"
    )
    token_count: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="消耗 token 数（估算）"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )

    session: Mapped["CounselorSession"] = relationship(
        "CounselorSession", back_populates="messages"
    )

    def __repr__(self):
        return f"<CounselorMessage(id={self.id}, role='{self.role}', mode='{self.mode}')>"


class CounselorLog(Base):
    """
    AI 助手问答日志表（独立归档）
    统计口径与教学问答完全分离，不并入"已解答率"等既有指标
    """
    __tablename__ = "counselor_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True, comment="会话ID"
    )
    user_id: Mapped[int] = mapped_column(
        Integer, nullable=False, index=True, comment="用户ID"
    )
    question: Mapped[str] = mapped_column(
        Text, nullable=False, comment="学生问题"
    )
    answer: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="助手回答"
    )
    mode: Mapped[Optional[str]] = mapped_column(
        String(16), nullable=True, comment="回答模式：knowledge / general"
    )
    source_titles: Mapped[Optional[list]] = mapped_column(
        JSON, nullable=True, comment="引用的知识库来源标题列表"
    )
    is_answered: Mapped[int] = mapped_column(
        Integer, default=1, comment="是否基于知识库命中：0=未命中, 1=命中"
    )
    feedback: Mapped[int] = mapped_column(
        Integer, default=0, comment="反馈：0=未反馈, 1=点赞, 2=点踩"
    )
    feedback_reason: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, comment="反馈原因"
    )
    retrieval_ms: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="检索耗时（毫秒）"
    )
    llm_ms: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="LLM 生成耗时（毫秒）"
    )
    total_ms: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="总耗时（毫秒）"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )

    def __repr__(self):
        return f"<CounselorLog(id={self.id}, session_id='{self.session_id}')>"
