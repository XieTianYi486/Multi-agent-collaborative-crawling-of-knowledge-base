# ============================================================
# AI 助手 请求/响应 Schema
# ============================================================

from typing import Optional

from pydantic import BaseModel, Field


class CounselorAskRequest(BaseModel):
    """AI 助手提问请求"""
    question: str = Field(..., min_length=1, max_length=1000, description="用户问题")
    session_id: Optional[str] = Field(
        default=None, description="会话ID（为空则自动新建会话）"
    )


class CounselorSessionCreate(BaseModel):
    """创建 AI 助手会话"""
    title: Optional[str] = Field(default="与 AI 助手的新对话", max_length=255)


class CounselorSessionUpdate(BaseModel):
    """更新 AI 助手会话"""
    title: Optional[str] = Field(default=None, max_length=255)


class CounselorFeedbackRequest(BaseModel):
    """AI 助手回答反馈"""
    session_id: str = Field(..., description="会话ID")
    feedback: int = Field(..., ge=0, le=2, description="0=取消, 1=点赞, 2=点踩")
    reason: Optional[str] = Field(default=None, max_length=255, description="反馈原因")
