# ============================================================
# 站内通知 API
# ============================================================

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.db.sqlite import get_db
from app.models.notification import Notification
from app.models.user import User
from app.schemas.common import APIResponse, PaginatedData
from app.services.notification_service import serialize

router = APIRouter(prefix="/notifications", tags=["消息通知"])


@router.get("", response_model=APIResponse, summary="我的通知列表")
def list_notifications(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    unread_only: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    query = db.query(Notification).filter(Notification.user_id == current_user.id)
    if unread_only:
        query = query.filter(Notification.is_read.is_(False))

    total = query.count()
    items = (
        query.order_by(Notification.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return APIResponse(
        code=0, message="success",
        data=PaginatedData.from_query(
            [serialize(n) for n in items], total, page, page_size
        ).model_dump(),
    )


@router.get("/unread-count", response_model=APIResponse, summary="未读通知数")
def unread_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    count = (
        db.query(Notification)
        .filter(
            Notification.user_id == current_user.id,
            Notification.is_read.is_(False),
        )
        .count()
    )
    return APIResponse(code=0, message="success", data={"count": count})


@router.put("/read-all", response_model=APIResponse, summary="全部标为已读")
def read_all(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    db.query(Notification).filter(
        Notification.user_id == current_user.id,
        Notification.is_read.is_(False),
    ).update({Notification.is_read: True})
    db.commit()
    return APIResponse(code=0, message="已全部标为已读")


@router.put("/{notification_id}/read", response_model=APIResponse, summary="标为已读")
def mark_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    notification = (
        db.query(Notification)
        .filter(
            Notification.id == notification_id,
            Notification.user_id == current_user.id,
        )
        .first()
    )
    if not notification:
        return APIResponse(code=1, message="通知不存在")
    notification.is_read = True
    db.commit()
    return APIResponse(code=0, message="已标为已读")
