# ============================================================
# 补采需求模型
# 知识库未命中 / 点踩的问题沉淀为采集需求，驱动爬虫补采
# ============================================================

from datetime import datetime

from sqlalchemy import Column, Integer, String, Text, DateTime

from app.db.sqlite import Base
from app.models.user import utcnow


class CollectionRequest(Base):
    """补采需求表：把未覆盖问题转为采集任务，形成补采闭环"""

    __tablename__ = "collection_requests"

    id = Column(Integer, primary_key=True, autoincrement=True)
    question = Column(Text, nullable=False, comment="待补采的问题")
    # 来源：missed=未命中(拒答) negative_feedback=点踩
    reason = Column(String(20), default="missed", nullable=False, comment="需求来源")
    # 状态流转：0=待处理 1=已触发采集 2=已完成 3=已忽略
    status = Column(Integer, default=0, nullable=False, index=True, comment="处理状态")
    category_id = Column(Integer, nullable=True, comment="建议归属分类ID（可选）")
    chat_log_id = Column(Integer, nullable=True, comment="关联问答日志ID（可选）")
    note = Column(Text, nullable=True, comment="处理备注")
    created_by = Column(Integer, nullable=False, index=True, comment="提交人用户ID")
    created_at = Column(DateTime, default=utcnow, nullable=False, comment="创建时间")
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, comment="更新时间")

    def __repr__(self):
        return f"<CollectionRequest(id={self.id}, status={self.status})>"
