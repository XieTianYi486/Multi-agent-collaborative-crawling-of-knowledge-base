# ============================================================
# 授课关系模型：老师 ↔ 班级
# 一个老师可教多个班，一个班可有多名任课老师；
# 教师端据此校验「能查看哪些班级的学生信息」
# ============================================================

from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, UniqueConstraint
)

from app.db.sqlite import Base
from app.models.user import utcnow


class TeachingAssignment(Base):
    __tablename__ = "teaching_assignments"
    __table_args__ = (
        UniqueConstraint("teacher_id", "class_id", name="uq_teaching_teacher_class"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    teacher_id = Column(
        Integer, ForeignKey("users.id"), nullable=False, index=True, comment="教师用户ID"
    )
    class_id = Column(
        Integer, ForeignKey("departments.id"), nullable=False, index=True, comment="班级部门ID"
    )
    subject = Column(String(64), nullable=True, comment="任教学科（可选）")
    created_at = Column(DateTime, default=utcnow, nullable=False, comment="分配时间")

    def __repr__(self):
        return f"<TeachingAssignment(id={self.id}, teacher={self.teacher_id}, class={self.class_id})>"
