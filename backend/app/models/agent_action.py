# ============================================================
# SQLAlchemy 数据模型 - AI 助手写操作确认令牌
#
# 令牌的「一次性」必须跨进程/跨重启成立，不能只存进程内存；
# 同时令牌 JWT 里只放 jti（参数存库），避免长中文参数把
# token 撑到超过接口 4000 字符上限导致确认卡永远无法提交。
# ============================================================

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.sqlite import Base
from app.models.user import utcnow


class AgentActionToken(Base):
    """AI 助手写操作确认令牌（服务端状态 + 短时 JWT 引用）"""

    __tablename__ = "agent_action_tokens"

    jti: Mapped[str] = mapped_column(
        String(32), primary_key=True, comment="令牌唯一 ID（JWT jti）"
    )
    user_id: Mapped[int] = mapped_column(
        Integer, nullable=False, index=True, comment="归属用户"
    )
    tool: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="待确认的工具名"
    )
    args_json: Mapped[str] = mapped_column(
        Text, nullable=False, comment="工具参数（JSON 字符串，不进入 JWT）"
    )
    session_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, comment="关联助手会话"
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, index=True, comment="过期时间"
    )
    consumed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, comment="消费时间（NULL=未消费）"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )
