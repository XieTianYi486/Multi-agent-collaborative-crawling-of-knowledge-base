# ============================================================
# 教学关系 Schema
# ============================================================

from typing import Optional

from pydantic import BaseModel, Field


class AssignmentCreate(BaseModel):
    teacher_id: int = Field(..., description="教师用户ID")
    class_id: int = Field(..., description="班级部门ID")
    subject: Optional[str] = Field(default=None, max_length=64, description="任教学科")
