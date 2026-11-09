# ============================================================
# 视频专区接口
# 学生端：浏览 / 筛选 / 搜索已上架视频
# 管理端：视频元数据增删改查、上下架、排序
# 仅保存 B 站元数据，播放走官方 iframe 播放器
# ============================================================

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, require_knowledge_admin
from app.core.exceptions import DuplicateException, NotFoundException
from app.db.sqlite import get_db
from app.models.user import User
from app.models.video import Video
from app.schemas.common import APIResponse, PaginatedData
from app.schemas.video import VideoCreate, VideoOut, VideoUpdate

router = APIRouter(prefix="/videos", tags=["视频专区"])
admin_router = APIRouter(prefix="/admin/videos", tags=["视频管理"])


# ==================== 学生端 ====================

@router.get("", response_model=APIResponse, summary="视频列表（已上架）")
def list_videos(
    keyword: Optional[str] = Query(default=None, max_length=100, description="标题/UP主/简介关键词"),
    category: Optional[str] = Query(default=None, description="方向分类"),
    difficulty: Optional[str] = Query(default=None, description="难度"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=12, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """浏览已上架视频，支持关键词、分类、难度筛选"""
    query = db.query(Video).filter(Video.status == 1)
    if category:
        query = query.filter(Video.category == category)
    if difficulty:
        query = query.filter(Video.difficulty == difficulty)
    if keyword:
        like = f"%{keyword.strip()}%"
        query = query.filter(or_(
            Video.title.like(like),
            Video.up_name.like(like),
            Video.description.like(like),
        ))

    total = query.count()
    items = (
        query.order_by(Video.sort_order.asc(), Video.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    data = [VideoOut.from_model(v).model_dump(mode="json") for v in items]
    return APIResponse(
        code=0, message="success",
        data=PaginatedData.from_query(data, total, page, page_size).model_dump(),
    )


@router.get("/categories", response_model=APIResponse, summary="视频分类及数量")
def list_video_categories(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """返回已上架视频的分类聚合，用于前端筛选栏"""
    rows = (
        db.query(Video.category, Video.id)
        .filter(Video.status == 1)
        .order_by(Video.sort_order.asc(), Video.id.asc())
        .all()
    )
    counts: dict[str, int] = {}
    for category, _ in rows:
        name = category or "其他"
        counts[name] = counts.get(name, 0) + 1
    data = [{"name": k, "count": v} for k, v in counts.items()]
    return APIResponse(code=0, message="success", data=data)


@router.get("/{video_id}", response_model=APIResponse, summary="视频详情")
def get_video(
    video_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取已上架视频详情"""
    video = db.query(Video).filter(Video.id == video_id, Video.status == 1).first()
    if not video:
        raise NotFoundException("视频不存在或已下架")
    return APIResponse(code=0, message="success", data=VideoOut.from_model(video).model_dump(mode="json"))


# ==================== 管理端 ====================

@admin_router.get("", response_model=APIResponse, summary="视频管理列表")
def admin_list_videos(
    keyword: Optional[str] = Query(default=None, max_length=100),
    category: Optional[str] = Query(default=None, max_length=64),
    status: Optional[int] = Query(default=None, ge=0, le=1),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_knowledge_admin),
):
    """管理端视频列表（含已下架）"""
    query = db.query(Video)
    if status is not None:
        query = query.filter(Video.status == status)
    if category:
        query = query.filter(Video.category == category)
    if keyword:
        like = f"%{keyword.strip()}%"
        query = query.filter(or_(
            Video.title.like(like),
            Video.bvid.like(like),
            Video.up_name.like(like),
        ))

    total = query.count()
    items = (
        query.order_by(Video.sort_order.asc(), Video.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    data = [VideoOut.from_model(v).model_dump(mode="json") for v in items]
    return APIResponse(
        code=0, message="success",
        data=PaginatedData.from_query(data, total, page, page_size).model_dump(),
    )


@admin_router.post("", response_model=APIResponse, summary="新增视频")
def create_video(
    payload: VideoCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_knowledge_admin),
):
    """新增视频元数据（bvid 唯一）"""
    if db.query(Video).filter(Video.bvid == payload.bvid).first():
        raise DuplicateException("该 BV 号已存在，请勿重复添加")

    video = Video(
        title=payload.title.strip(),
        bvid=payload.bvid,
        cover_url=payload.cover_url,
        up_name=payload.up_name,
        duration=payload.duration,
        play_count=payload.play_count,
        category=payload.category,
        difficulty=payload.difficulty,
        description=payload.description,
        tags=payload.tags,
        sort_order=payload.sort_order,
        status=payload.status,
    )
    db.add(video)
    db.flush()
    db.refresh(video)
    return APIResponse(
        code=0, message="视频已添加",
        data={"id": video.id, "url": f"https://www.bilibili.com/video/{video.bvid}"},
    )


@admin_router.put("/{video_id}", response_model=APIResponse, summary="编辑视频")
def update_video(
    video_id: int,
    payload: VideoUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_knowledge_admin),
):
    """编辑视频信息 / 上下架 / 调整排序"""
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise NotFoundException("视频不存在")

    updates = payload.model_dump(exclude_unset=True)
    new_bvid = updates.get("bvid")
    if new_bvid and new_bvid != video.bvid:
        if db.query(Video).filter(Video.bvid == new_bvid).first():
            raise DuplicateException("该 BV 号已存在，请勿重复添加")

    for field, value in updates.items():
        setattr(video, field, value)
    db.flush()
    return APIResponse(code=0, message="视频更新成功")


@admin_router.put("/{video_id}/status", response_model=APIResponse, summary="上架/下架")
def toggle_video_status(
    video_id: int,
    status: int = Query(..., ge=0, le=1, description="1=上架, 0=下架"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_knowledge_admin),
):
    """快速上架或下架视频"""
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise NotFoundException("视频不存在")
    video.status = status
    db.flush()
    return APIResponse(code=0, message="已上架" if status == 1 else "已下架")


@admin_router.delete("/{video_id}", response_model=APIResponse, summary="删除视频")
def delete_video(
    video_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_knowledge_admin),
):
    """删除视频元数据（不影响 B 站原视频）"""
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise NotFoundException("视频不存在")
    db.delete(video)
    db.flush()
    return APIResponse(code=0, message="视频已删除")
