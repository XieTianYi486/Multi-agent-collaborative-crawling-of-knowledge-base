# ============================================================
# SQLAlchemy 数据模型 - 开放 API 调用方
# 面向第三方系统的应用凭证（API Key），与登录用户体系分离
# ============================================================

from datetime import datetime
from typing import Optional

from sqlalchemy import Integer, String, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.db.sqlite import Base
from app.models.user import utcnow


class ApiClient(Base):
    """
    开放 API 调用方（应用凭证）

    与 users 表分离：面向"应用/系统"而非"人"。
    使用长期有效的 API Key 鉴权，不参与 RBAC 角色体系，
    可访问的文档密级上限由 security_level 单独控制（默认仅公开级）。
    """
    __tablename__ = "api_clients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="调用方名称"
    )
    key_hash: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True,
        comment="API Key 的 SHA-256（明文仅在创建时返回一次）"
    )
    description: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, comment="用途备注"
    )
    status: Mapped[int] = mapped_column(
        Integer, default=1, nullable=False, comment="状态：0=禁用, 1=启用"
    )
    security_level: Mapped[int] = mapped_column(
        Integer, default=1, nullable=False,
        comment="可访问密级上限：1=公开, 2=内部, 3=机密, 4=绝密"
    )
    call_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, comment="累计调用次数"
    )
    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, comment="最近一次调用时间"
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, comment="过期时间（NULL=永不过期）"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )

    def __repr__(self):
        return f"<ApiClient(id={self.id}, name='{self.name}')>"