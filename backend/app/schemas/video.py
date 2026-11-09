# ============================================================
# 视频专区 Schema
# 入库参数校验 + 出参结构
# ============================================================

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

BVID_PATTERN = r"^BV[0-9A-Za-z]{10}$"


class VideoCreate(BaseModel):
    """新增视频"""

    title: str = Field(..., min_length=1, max_length=300, description="视频标题")
    bvid: str = Field(..., pattern=BVID_PATTERN, description="B 站 BV 号")
    cover_url: Optional[str] = Field(default="", max_length=600, description="封面图地址")
    up_name: Optional[str] = Field(default="", max_length=128, description="UP 主名称")
    duration: int = Field(default=0, ge=0, description="时长（秒）")
    play_count: int = Field(default=0, ge=0, description="播放量")
    category: str = Field(default="嵌入式开发", max_length=64, description="方向分类")
    difficulty: str = Field(default="入门", max_length=32, description="难度")
    description: Optional[str] = Field(default="", description="视频简介")
    tags: list[str] = Field(default_factory=list, description="标签")
    sort_order: int = Field(default=0, description="排序号")
    status: int = Field(default=1, ge=0, le=1, description="1=上架, 0=下架")


class VideoUpdate(BaseModel):
    """编辑视频（字段均可选）"""

    title: Optional[str] = Field(default=None, min_length=1, max_length=300)
    bvid: Optional[str] = Field(default=None, pattern=BVID_PATTERN)
    cover_url: Optional[str] = Field(default=None, max_length=600)
    up_name: Optional[str] = Field(default=None, max_length=128)
    duration: Optional[int] = Field(default=None, ge=0)
    play_count: Optional[int] = Field(default=None, ge=0)
    category: Optional[str] = Field(default=None, max_length=64)
    difficulty: Optional[str] = Field(default=None, max_length=32)
    description: Optional[str] = None
    tags: Optional[list[str]] = None
    sort_order: Optional[int] = None
    status: Optional[int] = Field(default=None, ge=0, le=1)


class VideoOut(BaseModel):
    """视频出参"""

    id: int
    title: str
    bvid: str
    url: str
    cover_url: Optional[str] = ""
    up_name: Optional[str] = ""
    duration: int
    play_count: int
    category: str
    difficulty: str
    description: Optional[str] = ""
    tags: list[str]
    sort_order: int
    status: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @classmethod
    def from_model(cls, v) -> "VideoOut":
        return cls(
            id=v.id,
            title=v.title,
            bvid=v.bvid,
            url=f"https://www.bilibili.com/video/{v.bvid}",
            cover_url=v.cover_url or "",
            up_name=v.up_name or "",
            duration=v.duration or 0,
            play_count=v.play_count or 0,
            category=v.category,
            difficulty=v.difficulty,
            description=v.description or "",
            tags=list(v.tags or []),
            sort_order=v.sort_order or 0,
            status=v.status,
            created_at=v.created_at,
            updated_at=v.updated_at,
        )
