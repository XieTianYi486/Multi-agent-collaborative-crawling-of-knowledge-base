# ============================================================
# 站内通知服务
# ============================================================

from typing import Optional

from sqlalchemy.orm import Session

from app.models.notification import Notification


def notify(
    db: Session,
    user_id: Optional[int],
    ntype: str,
    title: str,
    content: str = "",
    link: Optional[str] = None,
) -> None:
    """写入一条站内通知（不提交事务，由调用方统一 commit）。"""
    if not user_id:
        return
    db.add(Notification(
        user_id=user_id,
        type=ntype,
        title=title,
        content=content,
        link=link,
        is_read=False,
    ))


def serialize(notification: Notification) -> dict:
    return {
        "id": notification.id,
        "type": notification.type,
        "title": notification.title,
        "content": notification.content,
        "link": notification.link,
        "is_read": notification.is_read,
        "created_at": (
            notification.created_at.isoformat() if notification.created_at else None
        ),
    }
