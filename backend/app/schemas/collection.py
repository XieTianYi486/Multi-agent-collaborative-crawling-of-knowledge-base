# ============================================================
# 补采需求相关 Pydantic Schema
# ============================================================

from typing import Optional

from pydantic import BaseModel, Field


class CollectionRequestCreate(BaseModel):
    """提交补采需求"""
    question: str = Field(..., min_length=1, max_length=2000, description="待补采的问题")
    reason: str = Field(default="missed", description="来源：missed / negative_feedback")
    category_id: Optional[int] = Field(default=None, description="建议归属分类ID")
    chat_log_id: Optional[int] = Field(default=None, description="关联问答日志ID")
    note: Optional[str] = Field(default=None, max_length=2000, description="补充说明")


class CollectionRequestUpdate(BaseModel):
    """更新补采需求（状态 / 备注）"""
    status: Optional[int] = Field(default=None, description="0待处理 1已触发 2已完成 3已忽略")
    note: Optional[str] = Field(default=None, max_length=2000, description="处理备注")
