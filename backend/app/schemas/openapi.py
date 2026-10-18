# ============================================================
# 开放 API 请求 Schema
# 供对外接口 /openapi/v1 使用，遵循项目 schemas 约定
# ============================================================

from typing import List, Optional

from pydantic import BaseModel, Field


class OpenSearchRequest(BaseModel):
    """对外检索请求"""
    query: str = Field(..., min_length=1, max_length=500, description="检索语句")
    top_k: int = Field(default=10, ge=1, le=50, description="返回片段数（1-50）")
    category_ids: Optional[List[int]] = Field(
        default=None, description="限定分类范围（可选，含所选分类的子孙分类）"
    )
    document_ids: Optional[List[int]] = Field(
        default=None, description="限定文档范围（可选）"
    )


class OpenAskRequest(BaseModel):
    """对外问答请求"""
    question: str = Field(..., min_length=1, max_length=1000, description="用户问题")
