# ============================================================
# 补采闭环接口
# 未命中 / 点踩问题 → 采集需求 → 触发爬虫补采 → 完成归档
# ============================================================

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, or_
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, require_knowledge_admin
from app.services.notification_service import notify
from app.db.sqlite import get_db
from app.models.chat import ChatLog
from app.models.collection import CollectionRequest
from app.models.user import User
from app.schemas.collection import (
    CollectionRequestCreate,
    CollectionRequestUpdate,
)
from app.schemas.common import APIResponse, PaginatedData

router = APIRouter(prefix="/collection", tags=["补采闭环"])

VALID_STATUS = {0, 1, 2, 3}
VALID_REASON = {"missed", "negative_feedback"}

STATUS_LABEL = {0: "待处理", 1: "已触发采集", 2: "已完成", 3: "已忽略"}

# 未关闭的需求（待处理 / 已触发采集）用于去重
OPEN_STATUS = (0, 1)


def _naive_utc_now() -> datetime:
    """SQLite 存储的 DATETIME 不带时区，统一用无时区 UTC 比较"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _serialize(r: CollectionRequest, creator_name: Optional[str]) -> dict:
    return {
        "id": r.id,
        "question": r.question,
        "reason": r.reason,
        "status": r.status,
        "status_label": STATUS_LABEL.get(r.status, "未知"),
        "category_id": r.category_id,
        "chat_log_id": r.chat_log_id,
        "note": r.note,
        "created_by": r.created_by,
        "creator_name": creator_name,
        "created_at": r.created_at,
        "updated_at": r.updated_at,
    }


# ==================== 未命中候选 ====================


@router.get("/candidates", response_model=APIResponse, summary="未命中问题候选")
def list_candidates(
    days: int = Query(default=30, ge=1, le=180, description="回溯天数"),
    limit: int = Query(default=20, ge=1, le=100, description="返回条数"),
    db: Session = Depends(get_db),
    _user: User = Depends(require_knowledge_admin),
):
    """聚合最近 N 天的未命中（拒答）或点踩问题，供管理员转为补采需求。

    已存在于补采队列且未关闭（待处理/已触发）的问题会被排除。
    """
    since = _naive_utc_now() - timedelta(days=days)

    rows = (
        db.query(
            ChatLog.question,
            func.count(ChatLog.id),
            func.max(ChatLog.created_at),
            func.sum(case((ChatLog.is_answered == 0, 1), else_=0)),
            func.sum(case((ChatLog.feedback == 2, 1), else_=0)),
        )
        .filter(ChatLog.created_at >= since)
        .filter(or_(ChatLog.is_answered == 0, ChatLog.feedback == 2))
        .group_by(ChatLog.question)
        .order_by(func.count(ChatLog.id).desc())
        .limit(limit * 3)
        .all()
    )

    open_questions = {
        q for (q,) in db.query(CollectionRequest.question)
        .filter(CollectionRequest.status.in_(OPEN_STATUS))
        .all()
    }

    data = []
    for question, count, last_at, missed, negative in rows:
        if question in open_questions:
            continue
        reasons = []
        if missed:
            reasons.append("missed")
        if negative:
            reasons.append("negative_feedback")
        data.append({
            "question": question,
            "count": int(count),
            "last_at": last_at,
            "missed_count": int(missed or 0),
            "negative_count": int(negative or 0),
            "reasons": reasons,
        })
        if len(data) >= limit:
            break

    return APIResponse(code=0, message="success", data={
        "items": data,
        "days": days,
        "pending_total": len(open_questions),
    })


# ==================== 补采需求 ====================


@router.post("/requests", response_model=APIResponse, summary="提交补采需求")
def create_request(
    data: CollectionRequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """登录用户提交补采需求；同一问题未关闭时幂等返回已有需求。"""
    question = data.question.strip()
    if not question:
        return APIResponse(code=1, message="问题内容不能为空")

    reason = data.reason if data.reason in VALID_REASON else "missed"

    existing = (
        db.query(CollectionRequest)
        .filter(CollectionRequest.question == question,
                CollectionRequest.status.in_(OPEN_STATUS))
        .first()
    )
    if existing:
        return APIResponse(code=0, message="该问题已在补采队列中", data={
            "id": existing.id,
            "duplicated": True,
        })

    req = CollectionRequest(
        question=question,
        reason=reason,
        status=0,
        category_id=data.category_id,
        chat_log_id=data.chat_log_id,
        note=data.note,
        created_by=current_user.id,
    )
    db.add(req)
    db.commit()
    db.refresh(req)

    return APIResponse(code=0, message="补采需求已提交", data={
        "id": req.id,
        "duplicated": False,
    })


@router.get("/requests/mine", response_model=APIResponse, summary="我的补采需求")
def list_my_requests(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: Optional[int] = Query(default=None, description="0待处理 1已触发 2已完成 3已忽略"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """当前用户提交的补采需求及处理状态，供学生/教师跟踪结果。"""
    query = db.query(CollectionRequest).filter(
        CollectionRequest.created_by == current_user.id
    )
    if status is not None and status in VALID_STATUS:
        query = query.filter(CollectionRequest.status == status)

    total = query.count()
    items = (
        query.order_by(CollectionRequest.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    creator_name = current_user.real_name or current_user.username
    data = [_serialize(r, creator_name) for r in items]
    return APIResponse(code=0, message="success", data=PaginatedData.from_query(
        data, total, page, page_size
    ).model_dump())


@router.get("/requests", response_model=APIResponse, summary="补采需求列表")
def list_requests(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: Optional[int] = Query(default=None, description="0待处理 1已触发 2已完成 3已忽略"),
    keyword: Optional[str] = Query(default=None, description="问题关键词"),
    db: Session = Depends(get_db),
    _user: User = Depends(require_knowledge_admin),
):
    """管理员查看补采需求队列，支持状态与关键词筛选。"""
    query = db.query(CollectionRequest)
    if status is not None and status in VALID_STATUS:
        query = query.filter(CollectionRequest.status == status)
    if keyword:
        query = query.filter(CollectionRequest.question.contains(keyword))
    # 待处理优先，其余按时间倒序
    query = query.order_by(CollectionRequest.status.asc(), CollectionRequest.id.desc())

    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()

    creator_ids = {r.created_by for r in items}
    names = {}
    if creator_ids:
        for u in db.query(User).filter(User.id.in_(creator_ids)).all():
            names[u.id] = u.real_name or u.username

    data = [_serialize(r, names.get(r.created_by)) for r in items]
    return APIResponse(code=0, message="success", data=PaginatedData.from_query(
        data, total, page, page_size
    ).model_dump())


@router.get("/requests/stats", response_model=APIResponse, summary="补采需求统计")
def request_stats(
    db: Session = Depends(get_db),
    _user: User = Depends(require_knowledge_admin),
):
    """各状态需求数量（用于管理页角标）。"""
    rows = (
        db.query(CollectionRequest.status, func.count(CollectionRequest.id))
        .group_by(CollectionRequest.status)
        .all()
    )
    counts = {str(s): 0 for s in VALID_STATUS}
    for s, c in rows:
        counts[str(s)] = int(c)
    counts["total"] = sum(counts[str(s)] for s in VALID_STATUS)
    return APIResponse(code=0, message="success", data=counts)


@router.put("/requests/{request_id}", response_model=APIResponse, summary="更新补采需求")
def update_request(
    request_id: int,
    data: CollectionRequestUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_knowledge_admin),
):
    """更新需求状态（完成 / 忽略 / 回退）或备注。"""
    req = db.query(CollectionRequest).filter(CollectionRequest.id == request_id).first()
    if not req:
        return APIResponse(code=1, message="补采需求不存在")

    old_status = req.status
    if data.status is not None:
        if data.status not in VALID_STATUS:
            return APIResponse(code=1, message="非法的需求状态")
        req.status = data.status
    if data.note is not None:
        req.note = data.note

    if data.status is not None and data.status != old_status and req.created_by != current_user.id:
        label = {0: "待处理", 1: "已触发采集", 2: "已完成", 3: "已忽略"}.get(req.status, "已更新")
        notify(
            db, req.created_by, "collection", "补采需求状态更新",
            f"你提交的补采「{req.question[:40]}」状态变为：{label}。",
            "/my-collections",
        )

    db.commit()
    db.refresh(req)
    return APIResponse(code=0, message="需求已更新", data=_serialize(req, None))


@router.post("/requests/{request_id}/run", response_model=APIResponse, summary="触发补采")
def run_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_knowledge_admin),
):
    """触发一次爬虫采集流水线，并把该需求标记为已触发采集。"""
    req = db.query(CollectionRequest).filter(CollectionRequest.id == request_id).first()
    if not req:
        return APIResponse(code=1, message="补采需求不存在")

    from crawler import runner

    started = runner.start_run(trigger="manual")
    if not started:
        return APIResponse(code=0, message="流水线已在运行中，请稍后再试", data={
            "started": False,
        })

    req.status = 1
    if req.created_by != current_user.id:
        notify(
            db, req.created_by, "collection", "补采需求已触发采集",
            f"你提交的补采「{req.question[:40]}」已进入采集队列。",
            "/my-collections",
        )
    db.commit()
    return APIResponse(code=0, message="已触发采集流水线", data={"started": True})
