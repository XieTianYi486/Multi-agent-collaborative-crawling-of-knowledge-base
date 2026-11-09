# ============================================================
# 站内通知模型：审核结果 / 工单回复 / 补采进度
# ============================================================

from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime
from app.db.sqlite import Base
from app.models.user import utcnow


class Notification(Base):
    """站内通知表"""

    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True, comment="接收人用户ID")
    type = Column(String(32), default="system", nullable=False, comment="通知类型")
    title = Column(String(256), nullable=False, comment="标题")
    content = Column(Text, nullable=True, comment="正文")
    link = Column(String(256), nullable=True, comment="点击跳转的前端路由")
    is_read = Column(Boolean, default=False, nullable=False, index=True, comment="是否已读")
    created_at = Column(DateTime, default=utcnow, nullable=False, comment="创建时间")
