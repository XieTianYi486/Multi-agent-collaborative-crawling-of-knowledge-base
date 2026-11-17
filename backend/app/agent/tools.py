# ============================================================
# AI 助手工具实现
#
# 所有工具都是现有业务 service / 数据表的薄封装，不新增业务逻辑：
#   - 只读工具：知识检索、资料查找、文档详情、我的补采/工单/通知、班级学生
#   - 写工具：提交补采、创建工单（必须先经用户确认）
#
# 每个 handler 自行打开/关闭数据库会话，返回值统一为：
#   {"ok": bool, "summary": str, "data": dict, "sources"?: list, "resources"?: list}
# ============================================================

from datetime import date, datetime, timedelta
import json
import re
from collections import Counter
from typing import Any, Dict, List, Optional

from sqlalchemy import func, or_

from app.agent.registry import (
    ADMIN_ROLES, ALL_ROLES, TEACHER_VIEW_ROLES, RISK_READ, RISK_WRITE,
    ToolContext, ToolPermissionError, ToolRegistry, ToolSpec,
)
from app.db.sqlite import SessionLocal
from app.models.audit import AuditLog
from app.models.chat import ChatLog
from app.models.collection import CollectionRequest
from app.models.document import Category, Document
from app.models.notification import Notification
from app.models.teaching import TeachingAssignment
from app.models.ticket import Ticket
from app.models.user import Department, Role, User, utcnow

COLLECTION_STATUS_LABEL = {
    0: "待处理", 1: "已触发采集", 2: "已完成", 3: "已忽略", 4: "未匹配资料",
}
TICKET_STATUS_LABEL = {
    "pending": "待处理", "processing": "处理中", "resolved": "已解决", "closed": "已关闭",
}


def _clip(text: Any, limit: int = 300) -> str:
    value = str(text or "")
    return value if len(value) <= limit else value[:limit] + "…"


def _ok(summary: str, data: Optional[Dict[str, Any]] = None, **extra) -> Dict[str, Any]:
    result: Dict[str, Any] = {"ok": True, "summary": summary, "data": data or {}}
    result.update(extra)
    return result


def _fail(summary: str, error: str = "") -> Dict[str, Any]:
    return {"ok": False, "summary": summary, "data": {"error": error or summary}}


# ---------- 学情 / 运营统计共用辅助 ----------

# 提问文本里高频但无信息量的词，避免热点词云被口水词占满
_QUESTION_STOPWORDS = frozenset({
    "什么", "怎么", "怎样", "如何", "为什么", "哪个", "哪些", "多少", "是否",
    "可以", "能否", "需要", "应该", "一个", "这个", "那个", "这些", "那些",
    "我们", "你们", "他们", "老师", "同学", "请问", "有没有", "以及", "还有",
    "就是", "然后", "现在", "一下", "一些", "有些", "东西", "问题", "麻烦",
})


def _window_start(days: int) -> datetime:
    """把天数限制在 1-90 天，返回窗口起点"""
    return utcnow() - timedelta(days=max(1, min(int(days), 90)))


def _age_days(moment: Optional[datetime]) -> int:
    """距今等待天数（用于判断积压时长）"""
    if moment is None:
        return 0
    return max(0, (utcnow() - moment).days)


def _keyword_ranking(questions: List[str], top_n: int = 10) -> List[Dict[str, Any]]:
    """用 jieba 对提问做分词并统计高频词；jieba 缺失时返回空列表"""
    try:
        import jieba
    except ImportError:  # pragma: no cover - 依赖缺失时降级
        return []

    counter: Counter = Counter()
    for question in questions:
        for raw in jieba.cut_for_search(str(question or "")):
            word = raw.strip().lower()
            if len(word) < 2 or word.isdigit() or word in _QUESTION_STOPWORDS:
                continue
            if not re.search(r"[0-9a-zA-Z\u4e00-\u9fff]", word):
                continue
            counter[word] += 1

    # 样本少时保留只出现一次的词，样本多时只保留真正的高频词
    min_count = 2 if len(questions) >= 8 else 1
    return [
        {"keyword": word, "count": count}
        for word, count in counter.most_common(top_n) if count >= min_count
    ]


def _load_class_for_ctx(db, ctx: ToolContext, class_id: int) -> Optional[Department]:
    """按 ID 取班级并校验教师任教关系；班级不存在返回 None"""
    dept = db.query(Department).filter(Department.id == class_id).first()
    if dept is None or dept.dept_type != "class":
        return None
    if ctx.role_code == "teacher":
        owned = (
            db.query(TeachingAssignment.id)
            .filter(
                TeachingAssignment.teacher_id == ctx.user_id,
                TeachingAssignment.class_id == class_id,
            )
            .first()
        )
        if owned is None:
            raise ToolPermissionError("你没有任教该班级，无法查看该班级数据")
    return dept


def _class_student_ids(db, class_name: str) -> List[int]:
    """班级学生 ID 列表（按部门名称关联，与既有教师端逻辑一致）"""
    rows = (
        db.query(User.id)
        .join(Role, User.role_id == Role.id)
        .filter(
            Role.code == "student",
            User.status == 1,
            User.department == class_name,
        )
        .all()
    )
    return [row[0] for row in rows]


def _class_logs(
    db, student_ids: List[int], since: datetime,
    only_unanswered: bool = False, limit: int = 500,
) -> List[ChatLog]:
    """班级学生提问日志（按时间倒序，最多 limit 条）"""
    if not student_ids:
        return []
    query = db.query(ChatLog).filter(
        ChatLog.user_id.in_(student_ids),
        ChatLog.created_at >= since,
    )
    if only_unanswered:
        query = query.filter(ChatLog.is_answered == 0)
    return query.order_by(ChatLog.created_at.desc()).limit(limit).all()


# ==================== 只读工具 ====================


def _search_knowledge(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    """语义 + 关键词混合检索知识库片段"""
    from app.services.chat_service import get_chat_service

    query = str(args.get("query") or "").strip()
    if not query:
        return _fail("缺少检索内容")

    top_k = max(1, min(int(args.get("top_k") or 5), 8))
    chunks = get_chat_service().search_chunks(
        query=query, security_level=ctx.security_level, top_k=top_k,
    )

    items: List[Dict[str, Any]] = []
    sources: List[Dict[str, Any]] = []
    for c in chunks:
        item = {
            "document_id": c.get("document_id", 0),
            "document_name": c.get("document_name", ""),
            "chapter": c.get("chapter", ""),
            "page": c.get("page", 1),
            "content": _clip(c.get("content", ""), 600),
            "source_url": c.get("source_url", ""),
            "score": round(float(c.get("score", 0)), 4),
        }
        items.append(item)
        sources.append({
            "document_id": item["document_id"],
            "document_name": item["document_name"],
            "chapter": item["chapter"],
            "page": item["page"],
            "snippet": _clip(c.get("content", ""), 200),
            "score": item["score"],
            "source_url": item["source_url"],
            "authority_weight": c.get("authority_weight", 1.0),
            "authority_label": c.get("authority_label", ""),
            "source_site": c.get("source_site", ""),
        })

    if not items:
        return _ok("知识库没有检索到相关资料", {"items": []}, sources=[])

    return _ok(
        f"知识库检索到 {len(items)} 条相关资料",
        {"items": items},
        sources=sources,
    )


def _search_resources(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    """查找可跳转的文档 / 视频条目"""
    from app.services.resource_service import search_resources

    query = str(args.get("query") or "").strip()
    if not query:
        return _fail("缺少检索内容")

    db = SessionLocal()
    try:
        # force=True：此处已由 Agent 判定为找资料意图，不再做关键词二次门控
        resources = search_resources(
            db, query, ctx.security_level, force=True,
        )
    finally:
        db.close()

    if not resources:
        return _ok("没有找到匹配的文档或视频", {"items": []}, resources=[])

    return _ok(
        f"找到 {len(resources)} 个可打开的资料",
        {"items": resources},
        resources=resources,
    )


def _get_document_detail(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    """按文档 ID 获取详情（仅返回当前用户有权查看的已发布文档）"""
    doc_id = int(args.get("document_id") or 0)
    today = date.today()

    db = SessionLocal()
    try:
        doc = (
            db.query(Document)
            .filter(
                Document.id == doc_id,
                Document.status == 1,
                Document.review_status == 2,
                Document.security_level <= ctx.security_level,
                or_(Document.expire_date.is_(None), Document.expire_date >= today),
            )
            .first()
        )
        if doc is None:
            return _fail("文档不存在、未发布或无权查看")

        data = {
            "id": doc.id,
            "title": doc.title,
            "file_name": doc.file_name,
            "file_type": doc.file_type,
            "category": doc.category.name if doc.category else None,
            "tags": doc.tags,
            "chunk_count": doc.chunk_count,
            "source_url": doc.source_url,
            "publish_date": doc.publish_date.isoformat() if doc.publish_date else None,
            "created_at": doc.created_at.isoformat() if doc.created_at else None,
        }
        return _ok(f"已找到文档《{doc.title}》", data)
    finally:
        db.close()


def _list_my_collections(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    """查看当前用户提交的补采需求及状态"""
    status = args.get("status")

    db = SessionLocal()
    try:
        query = db.query(CollectionRequest).filter(
            CollectionRequest.created_by == ctx.user_id
        )
        if status is not None:
            query = query.filter(CollectionRequest.status == int(status))
        rows = query.order_by(CollectionRequest.id.desc()).limit(10).all()

        items = [
            {
                "id": r.id,
                "question": _clip(r.question, 120),
                "status": r.status,
                "status_label": COLLECTION_STATUS_LABEL.get(r.status, "未知"),
                "note": _clip(r.note, 120),
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
        if not items:
            return _ok("你还没有提交过补采需求", {"items": []})
        return _ok(f"你共有 {len(items)} 条补采需求", {"items": items})
    finally:
        db.close()


def _list_my_tickets(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    """查看当前用户提交的工单及处理进度"""
    status = args.get("status")

    db = SessionLocal()
    try:
        query = db.query(Ticket).filter(Ticket.created_by == ctx.user_id)
        if status:
            query = query.filter(Ticket.status == str(status))
        rows = query.order_by(Ticket.id.desc()).limit(10).all()

        items = [
            {
                "id": t.id,
                "title": _clip(t.title, 120),
                "status": t.status,
                "status_label": TICKET_STATUS_LABEL.get(t.status, t.status),
                "reply": _clip(t.reply, 300) if t.reply else None,
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "updated_at": t.updated_at.isoformat() if t.updated_at else None,
            }
            for t in rows
        ]
        if not items:
            return _ok("你还没有提交过工单", {"items": []})
        return _ok(f"你共有 {len(items)} 条工单", {"items": items})
    finally:
        db.close()


def _list_notifications(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    """查看当前用户的站内通知（默认只看未读）"""
    unread_only = bool(args.get("unread_only", True))

    db = SessionLocal()
    try:
        query = db.query(Notification).filter(Notification.user_id == ctx.user_id)
        if unread_only:
            query = query.filter(Notification.is_read.is_(False))
        rows = query.order_by(Notification.id.desc()).limit(10).all()

        items = [
            {
                "id": n.id,
                "type": n.type,
                "title": n.title,
                "content": _clip(n.content, 200),
                "link": n.link,
                "is_read": bool(n.is_read),
                "created_at": n.created_at.isoformat() if n.created_at else None,
            }
            for n in rows
        ]
        if not items:
            return _ok("暂无未读通知" if unread_only else "暂无通知", {"items": []})
        return _ok(f"共 {len(items)} 条通知", {"items": items})
    finally:
        db.close()


def _list_my_classes(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    """教师查看自己任教的班级，管理员查看全部班级"""
    db = SessionLocal()
    try:
        query = db.query(TeachingAssignment)
        if ctx.role_code == "teacher":
            query = query.filter(TeachingAssignment.teacher_id == ctx.user_id)
        assignments = query.order_by(TeachingAssignment.class_id).all()

        class_ids = {a.class_id for a in assignments}
        depts = (
            db.query(Department).filter(Department.id.in_(class_ids)).all()
            if class_ids else []
        )
        dept_map = {d.id: d for d in depts}

        student_counts: Dict[str, int] = {}
        if depts:
            rows = (
                db.query(User.department, func.count(User.id))
                .join(Role, User.role_id == Role.id)
                .filter(
                    Role.code == "student",
                    User.status == 1,
                    User.department.in_([d.name for d in depts]),
                )
                .group_by(User.department)
                .all()
            )
            student_counts = {name: count for name, count in rows}

        items = []
        for a in assignments:
            dept = dept_map.get(a.class_id)
            if dept is None:
                continue
            items.append({
                "class_id": a.class_id,
                "class_name": dept.name,
                "subject": a.subject,
                "student_count": student_counts.get(dept.name, 0),
            })

        if not items:
            return _ok("你目前没有任教班级", {"items": []})
        return _ok(f"你共任教 {len(items)} 个班级", {"items": items})
    finally:
        db.close()


def _class_students(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    """查看班级学生名单与学习概况（教师仅限本人任教班级）"""
    class_id = int(args.get("class_id") or 0)

    db = SessionLocal()
    try:
        dept = db.query(Department).filter(Department.id == class_id).first()
        if dept is None or dept.dept_type != "class":
            return _fail("班级不存在")

        if ctx.role_code == "teacher":
            owned = (
                db.query(TeachingAssignment)
                .filter(
                    TeachingAssignment.teacher_id == ctx.user_id,
                    TeachingAssignment.class_id == class_id,
                )
                .first()
            )
            if owned is None:
                raise ToolPermissionError("你没有任教该班级，无法查看学生信息")

        students = (
            db.query(User)
            .join(Role, User.role_id == Role.id)
            .filter(
                Role.code == "student",
                User.status == 1,
                User.department == dept.name,
            )
            .order_by(User.id.desc())
            .limit(20)
            .all()
        )
        ids = [s.id for s in students]

        chat_counts: Dict[int, int] = {}
        last_ask: Dict[int, Any] = {}
        if ids:
            chat_counts = dict(
                db.query(ChatLog.user_id, func.count(ChatLog.id))
                .filter(ChatLog.user_id.in_(ids))
                .group_by(ChatLog.user_id)
                .all()
            )
            last_ask = dict(
                db.query(ChatLog.user_id, func.max(ChatLog.created_at))
                .filter(ChatLog.user_id.in_(ids))
                .group_by(ChatLog.user_id)
                .all()
            )

        items = [
            {
                "id": s.id,
                "name": s.real_name or s.username,
                "username": s.username,
                "chat_count": chat_counts.get(s.id, 0),
                "last_ask_at": (
                    last_ask[s.id].isoformat() if last_ask.get(s.id) else None
                ),
            }
            for s in students
        ]
        return _ok(f"{dept.name} 共 {len(items)} 名学生", {
            "class_id": dept.id,
            "class_name": dept.name,
            "items": items,
        })
    finally:
        db.close()


def _class_question_hotspots(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    """班级近 N 天提问热点：高频关键词 + 活跃人数"""
    class_id = int(args.get("class_id") or 0)
    days = int(args.get("days") or 7)
    top_n = int(args.get("top_n") or 10)

    db = SessionLocal()
    try:
        dept = _load_class_for_ctx(db, ctx, class_id)
        if dept is None:
            return _fail("班级不存在")

        student_ids = _class_student_ids(db, dept.name)
        logs = _class_logs(db, student_ids, _window_start(days))
        keywords = _keyword_ranking([item.question for item in logs], top_n)
        active_students = len({item.user_id for item in logs})
        head = "、".join(k["keyword"] for k in keywords[:5]) or "暂无高频词"

        return _ok(
            f"{dept.name} 近 {days} 天有 {active_students} 名学生提问 {len(logs)} 次，"
            f"高频关键词：{head}",
            {
                "class_id": dept.id,
                "class_name": dept.name,
                "student_total": len(student_ids),
                "active_students": active_students,
                "question_count": len(logs),
                "keywords": keywords,
                "samples": [
                    {
                        "question": _clip(item.question, 80),
                        "asked_at": item.created_at.isoformat(),
                    }
                    for item in logs[:5]
                ],
            },
        )
    finally:
        db.close()


def _class_unanswered_questions(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    """班级近 N 天知识库未命中（拒答）的问题，指向知识缺口"""
    class_id = int(args.get("class_id") or 0)
    days = int(args.get("days") or 7)
    limit = int(args.get("limit") or 10)

    db = SessionLocal()
    try:
        dept = _load_class_for_ctx(db, ctx, class_id)
        if dept is None:
            return _fail("班级不存在")

        student_ids = _class_student_ids(db, dept.name)
        logs = _class_logs(
            db, student_ids, _window_start(days),
            only_unanswered=True, limit=limit,
        )
        name_map: Dict[int, str] = {}
        if student_ids:
            name_map = {
                u.id: (u.real_name or u.username)
                for u in db.query(User).filter(User.id.in_(student_ids)).all()
            }

        items = [
            {
                "question": _clip(item.question, 120),
                "student": name_map.get(item.user_id, "未知学生"),
                "asked_at": item.created_at.isoformat(),
            }
            for item in logs
        ]
        return _ok(
            f"{dept.name} 近 {days} 天有 {len(items)} 个问题知识库未能回答，"
            "建议补充相关资料或转人工",
            {
                "class_id": dept.id,
                "class_name": dept.name,
                "items": items,
            },
        )
    finally:
        db.close()


def _student_learning_profile(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    """单个学生的学习画像：累计/近期提问、未命中次数、最近提问"""
    class_id = int(args.get("class_id") or 0)
    student_id = int(args.get("student_id") or 0)
    days = int(args.get("days") or 7)

    db = SessionLocal()
    try:
        dept = _load_class_for_ctx(db, ctx, class_id)
        if dept is None:
            return _fail("班级不存在")

        student = db.query(User).filter(User.id == student_id).first()
        if student is None:
            return _fail("学生不存在")
        if student.department != dept.name:
            return _fail("该学生不属于这个班级")

        since = _window_start(days)
        total = (
            db.query(func.count(ChatLog.id))
            .filter(ChatLog.user_id == student_id)
            .scalar() or 0
        )
        recent_logs = (
            db.query(ChatLog)
            .filter(ChatLog.user_id == student_id, ChatLog.created_at >= since)
            .order_by(ChatLog.created_at.desc())
            .all()
        )
        unanswered = sum(1 for item in recent_logs if item.is_answered == 0)
        last_ask = max((item.created_at for item in recent_logs), default=None)
        name = student.real_name or student.username

        return _ok(
            f"{name} 累计提问 {int(total)} 次，近 {days} 天提问 {len(recent_logs)} 次，"
            f"其中 {unanswered} 次知识库未命中"
            + (f"，最近提问 {last_ask.strftime('%m-%d %H:%M')}" if last_ask else ""),
            {
                "student_id": student.id,
                "name": name,
                "class_name": dept.name,
                "total_questions": int(total),
                "recent_questions": len(recent_logs),
                "unanswered_recent": unanswered,
                "last_ask_at": last_ask.isoformat() if last_ask else None,
                "recent_items": [
                    {
                        "question": _clip(item.question, 80),
                        "answered": bool(item.is_answered),
                        "asked_at": item.created_at.isoformat(),
                    }
                    for item in recent_logs[:5]
                ],
            },
        )
    finally:
        db.close()


def _class_teaching_report(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    """班级学情周报：提问量、参与度、未命中、热点与待补充方向"""
    class_id = int(args.get("class_id") or 0)
    days = int(args.get("days") or 7)

    db = SessionLocal()
    try:
        dept = _load_class_for_ctx(db, ctx, class_id)
        if dept is None:
            return _fail("班级不存在")

        student_ids = _class_student_ids(db, dept.name)
        logs = _class_logs(db, student_ids, _window_start(days))
        unanswered_logs = [item for item in logs if item.is_answered == 0]
        keywords = _keyword_ranking([item.question for item in logs], 5)

        # 未命中问题按原文聚合，便于直接转补采
        gap_counter: Counter = Counter(
            _clip(item.question, 80) for item in unanswered_logs
        )
        gaps = [
            {"question": question, "count": count}
            for question, count in gap_counter.most_common(5)
        ]
        active_students = len({item.user_id for item in logs})
        head = "、".join(k["keyword"] for k in keywords) or "无"

        return _ok(
            f"{dept.name} 近 {days} 天学情：{len(student_ids)} 名学生中 {active_students} 人参与提问，"
            f"共 {len(logs)} 次，未命中 {len(unanswered_logs)} 次；热点：{head}",
            {
                "class_id": dept.id,
                "class_name": dept.name,
                "days": days,
                "student_total": len(student_ids),
                "active_students": active_students,
                "question_count": len(logs),
                "unanswered_count": len(unanswered_logs),
                "keywords": keywords,
                "gaps": gaps,
            },
        )
    finally:
        db.close()


def _get_admin_overview(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    """管理员查看待办概览：待审核文档、待处理补采、待处理工单"""
    db = SessionLocal()
    try:
        pending_docs = (
            db.query(func.count(Document.id))
            .filter(Document.review_status == 1)
            .scalar() or 0
        )
        pending_collections = (
            db.query(func.count(CollectionRequest.id))
            .filter(CollectionRequest.status.in_((0, 1)))
            .scalar() or 0
        )
        pending_tickets = (
            db.query(func.count(Ticket.id))
            .filter(Ticket.status.in_(("pending", "processing")))
            .scalar() or 0
        )
        return _ok(
            "待办概览：待审核文档 {} 篇，待处理补采 {} 条，待处理工单 {} 条".format(
                pending_docs, pending_collections, pending_tickets
            ),
            {
                "pending_documents": int(pending_docs),
                "pending_collections": int(pending_collections),
                "pending_tickets": int(pending_tickets),
            },
        )
    finally:
        db.close()


def _list_pending_documents(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    """待审核文档列表（按提交时间从早到晚，便于先审最早积压）"""
    limit = int(args.get("limit") or 10)
    category_id = args.get("category_id")

    db = SessionLocal()
    try:
        query = db.query(Document).filter(Document.review_status == 1)
        if category_id:
            query = query.filter(Document.category_id == int(category_id))
        total = query.count()
        docs = query.order_by(Document.created_at.asc()).limit(limit).all()

        category_ids = {d.category_id for d in docs if d.category_id}
        category_map: Dict[int, str] = {}
        if category_ids:
            category_map = {
                c.id: c.name
                for c in db.query(Category).filter(Category.id.in_(category_ids)).all()
            }
        uploader_ids = {d.created_by for d in docs if d.created_by}
        uploader_map: Dict[int, str] = {}
        if uploader_ids:
            uploader_map = {
                u.id: (u.real_name or u.username)
                for u in db.query(User).filter(User.id.in_(uploader_ids)).all()
            }

        items = [
            {
                "document_id": doc.id,
                "title": _clip(doc.title, 60),
                "category": category_map.get(doc.category_id, "未分类"),
                "uploader": uploader_map.get(doc.created_by, "未知"),
                "waiting_days": _age_days(doc.created_at),
                "created_at": doc.created_at.isoformat(),
            }
            for doc in docs
        ]
        if not items:
            return _ok("当前没有待审核文档", {"total": 0, "items": []})

        oldest = items[0]["waiting_days"]
        return _ok(
            f"当前共 {total} 篇待审核文档，最早一篇已等待 {oldest} 天",
            {
                "total": total,
                "items": items,
                "overdue": [i for i in items if i["waiting_days"] >= 3],
            },
        )
    finally:
        db.close()


def _list_pending_work(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    """待处理补采需求与工单队列（含等待时长）"""
    limit = int(args.get("limit") or 10)

    db = SessionLocal()
    try:
        collection_query = db.query(CollectionRequest).filter(
            CollectionRequest.status.in_((0, 1))
        )
        ticket_query = db.query(Ticket).filter(
            Ticket.status.in_(("pending", "processing"))
        )
        collection_total = collection_query.count()
        ticket_total = ticket_query.count()

        collections = (
            collection_query.order_by(CollectionRequest.created_at.asc())
            .limit(limit).all()
        )
        tickets = (
            ticket_query.order_by(Ticket.created_at.asc()).limit(limit).all()
        )

        collection_items = [
            {
                "id": item.id,
                "question": _clip(item.question, 80),
                "status": COLLECTION_STATUS_LABEL.get(item.status, str(item.status)),
                "waiting_days": _age_days(item.created_at),
            }
            for item in collections
        ]
        ticket_items = [
            {
                "id": item.id,
                "title": _clip(item.title, 60),
                "status": TICKET_STATUS_LABEL.get(item.status, item.status),
                "priority": item.priority,
                "waiting_days": _age_days(item.created_at),
            }
            for item in tickets
        ]

        max_collection_wait = max(
            (i["waiting_days"] for i in collection_items), default=0
        )
        max_ticket_wait = max((i["waiting_days"] for i in ticket_items), default=0)
        return _ok(
            f"待处理补采 {collection_total} 条（最长等待 {max_collection_wait} 天），"
            f"待处理工单 {ticket_total} 条（最长等待 {max_ticket_wait} 天）",
            {
                "collection_total": collection_total,
                "ticket_total": ticket_total,
                "collections": collection_items,
                "tickets": ticket_items,
            },
        )
    finally:
        db.close()


def _knowledge_gap_report(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    """知识缺口报告：近 N 天未命中问题按原文聚合"""
    days = int(args.get("days") or 7)
    limit = int(args.get("limit") or 10)

    db = SessionLocal()
    try:
        rows = (
            db.query(
                ChatLog.question,
                func.count(ChatLog.id).label("count"),
                func.max(ChatLog.created_at).label("last_at"),
            )
            .filter(
                ChatLog.is_answered == 0,
                ChatLog.created_at >= _window_start(days),
            )
            .group_by(ChatLog.question)
            .order_by(func.count(ChatLog.id).desc())
            .limit(limit)
            .all()
        )
        pending_collections = (
            db.query(func.count(CollectionRequest.id))
            .filter(CollectionRequest.status == 0)
            .scalar() or 0
        )
        items = [
            {
                "question": _clip(row.question, 100),
                "count": int(row.count),
                "last_asked_at": row.last_at.isoformat() if row.last_at else None,
            }
            for row in rows
        ]
        if not items:
            return _ok(
                f"近 {days} 天没有未命中的问题，知识覆盖情况良好",
                {"items": [], "pending_collections": int(pending_collections)},
            )
        return _ok(
            f"近 {days} 天共 {sum(i['count'] for i in items)} 次未命中，"
            f"集中在 {len(items)} 类问题，另有 {int(pending_collections)} 条补采待处理",
            {
                "days": days,
                "items": items,
                "pending_collections": int(pending_collections),
            },
        )
    finally:
        db.close()


def _platform_usage_stats(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    """平台使用情况：提问量、活跃人数、已解答率、热门资料"""
    days = int(args.get("days") or 7)

    db = SessionLocal()
    try:
        since = _window_start(days)
        base = db.query(ChatLog).filter(ChatLog.created_at >= since)
        total = base.count()
        answered = base.filter(ChatLog.is_answered == 1).count()
        active_users = (
            db.query(func.count(func.distinct(ChatLog.user_id)))
            .filter(ChatLog.created_at >= since)
            .scalar() or 0
        )
        trend_rows = (
            db.query(func.date(ChatLog.created_at), func.count(ChatLog.id))
            .filter(ChatLog.created_at >= since)
            .group_by(func.date(ChatLog.created_at))
            .order_by(func.date(ChatLog.created_at))
            .all()
        )
        trend = [
            {"date": str(day), "count": int(count)} for day, count in trend_rows
        ]

        # 被引用最多的资料（source_doc_ids 是 JSON 数组）
        doc_counter: Counter = Counter()
        for (source_ids,) in (
            db.query(ChatLog.source_doc_ids)
            .filter(
                ChatLog.created_at >= since,
                ChatLog.source_doc_ids.isnot(None),
            )
            .all()
        ):
            ids = source_ids
            if isinstance(ids, str):
                try:
                    ids = json.loads(ids)
                except (TypeError, ValueError):
                    continue
            if isinstance(ids, list):
                doc_counter.update(int(i) for i in ids if str(i).isdigit())

        top_docs: List[Dict[str, Any]] = []
        if doc_counter:
            doc_ids = [doc_id for doc_id, _ in doc_counter.most_common(5)]
            title_map = {
                d.id: d.title
                for d in db.query(Document).filter(Document.id.in_(doc_ids)).all()
            }
            top_docs = [
                {"document_id": doc_id, "title": _clip(title_map.get(doc_id, "已删除文档"), 60),
                 "cited": count}
                for doc_id, count in doc_counter.most_common(5)
            ]

        rate = round(answered * 100.0 / total, 1) if total else 0.0
        return _ok(
            f"近 {days} 天共 {total} 次提问，{int(active_users)} 名用户参与，"
            f"已解答率 {rate}%",
            {
                "days": days,
                "total_questions": total,
                "active_users": int(active_users),
                "answered": answered,
                "answered_rate": rate,
                "trend": trend,
                "top_documents": top_docs,
            },
        )
    finally:
        db.close()


def _account_overview(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    """账号概览：角色分布、启停状态、班级数、近期登录人数"""
    days = int(args.get("days") or 30)

    db = SessionLocal()
    try:
        role_rows = (
            db.query(Role.code, Role.name, func.count(User.id))
            .outerjoin(User, User.role_id == Role.id)
            .group_by(Role.code, Role.name)
            .all()
        )
        roles = [
            {"code": code, "name": name, "count": int(count)}
            for code, name, count in role_rows
        ]
        total = db.query(func.count(User.id)).scalar() or 0
        active = (
            db.query(func.count(User.id)).filter(User.status == 1).scalar() or 0
        )
        class_count = (
            db.query(func.count(Department.id))
            .filter(Department.dept_type == "class")
            .scalar() or 0
        )
        recent_login = (
            db.query(func.count(func.distinct(AuditLog.user_id)))
            .filter(
                AuditLog.module == "login",
                AuditLog.action == "login_success",
                AuditLog.created_at >= _window_start(days),
            )
            .scalar() or 0
        )

        role_head = "、".join(
            f"{item['name']} {item['count']}" for item in roles if item["count"]
        ) or "暂无账号"
        return _ok(
            f"共 {total} 个账号（{role_head}），{class_count} 个班级，"
            f"近 {days} 天 {int(recent_login)} 人登录过",
            {
                "total_users": int(total),
                "active_users": int(active),
                "disabled_users": int(total) - int(active),
                "class_count": int(class_count),
                "recent_login_users": int(recent_login),
                "roles": roles,
            },
        )
    finally:
        db.close()


def _audit_summary(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    """审计摘要：近 N 天关键操作分布、敏感词命中、被拦截操作"""
    days = int(args.get("days") or 7)
    limit = int(args.get("limit") or 10)

    db = SessionLocal()
    try:
        since = _window_start(days)
        rows = (
            db.query(
                AuditLog.module, AuditLog.action, AuditLog.status,
                func.count(AuditLog.id).label("count"),
            )
            .filter(AuditLog.created_at >= since)
            .group_by(AuditLog.module, AuditLog.action, AuditLog.status)
            .order_by(func.count(AuditLog.id).desc())
            .limit(limit)
            .all()
        )
        items = [
            {
                "module": module,
                "action": action,
                "status": status,
                "count": int(count),
            }
            for module, action, status, count in rows
        ]
        total = (
            db.query(func.count(AuditLog.id))
            .filter(AuditLog.created_at >= since)
            .scalar() or 0
        )
        blocked = (
            db.query(func.count(AuditLog.id))
            .filter(
                AuditLog.created_at >= since,
                AuditLog.status == "blocked",
            )
            .scalar() or 0
        )
        sensitive = (
            db.query(func.count(AuditLog.id))
            .filter(
                AuditLog.created_at >= since,
                AuditLog.action.like("%sensitive%"),
            )
            .scalar() or 0
        )
        return _ok(
            f"近 {days} 天共 {int(total)} 条审计记录，其中拦截 {int(blocked)} 次、"
            f"敏感词命中 {int(sensitive)} 次",
            {
                "days": days,
                "total": int(total),
                "blocked": int(blocked),
                "sensitive_hits": int(sensitive),
                "items": items,
            },
        )
    finally:
        db.close()


# ==================== 写工具（需用户确认） ====================


def _submit_collection_request(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    """提交知识库补采需求（同一问题未关闭时幂等）"""
    question = str(args.get("question") or "").strip()
    if not question:
        return _fail("补采问题不能为空")

    reason = str(args.get("reason") or "missed")
    if reason not in ("missed", "negative_feedback"):
        reason = "missed"

    db = SessionLocal()
    try:
        existing = (
            db.query(CollectionRequest)
            .filter(
                CollectionRequest.question == question,
                CollectionRequest.status.in_((0, 1)),
            )
            .first()
        )
        if existing is not None:
            return _ok(
                f"该问题已在补采队列中（需求 #{existing.id}），无需重复提交",
                {"id": existing.id, "duplicated": True},
            )

        req = CollectionRequest(
            question=question,
            reason=reason,
            status=0,
            note=str(args.get("note") or "")[:500] or None,
            created_by=ctx.user_id,
        )
        db.add(req)
        db.commit()
        db.refresh(req)
        return _ok(
            f"已提交补采需求 #{req.id}，管理员触发采集后会通知你",
            {"id": req.id, "duplicated": False},
        )
    finally:
        db.close()


def _create_ticket(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    """创建人工兜底工单"""
    title = str(args.get("title") or "").strip()
    question = str(args.get("question") or "").strip()
    if not title or not question:
        return _fail("工单标题和问题内容不能为空")

    priority = str(args.get("priority") or "medium")
    if priority not in ("high", "medium", "low"):
        priority = "medium"

    db = SessionLocal()
    try:
        ticket = Ticket(
            title=_clip(title, 250),
            question=question,
            detail=str(args.get("detail") or "")[:2000] or None,
            session_id=ctx.session_id,
            priority=priority,
            created_by=ctx.user_id,
            status="pending",
        )
        db.add(ticket)
        db.commit()
        db.refresh(ticket)
        return _ok(
            f"工单 #{ticket.id} 已提交，老师回复后会通过站内通知提醒你",
            {"id": ticket.id, "status": "pending", "status_label": "待处理"},
        )
    finally:
        db.close()


# ==================== 注册 ====================


def register_all(registry: ToolRegistry) -> None:
    """把所有工具注册到注册表（由 get_tool_registry 调用一次）"""
    specs = [
        ToolSpec(
            name="search_knowledge",
            label="检索知识库",
            description=(
                "在学院教学知识库中做语义+关键词混合检索，返回相关文档片段与来源。"
                "适合回答概念、原理、接线、代码示例等知识性问题，也可用于先确认知识库是否有相关资料。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "检索语句，尽量保留专业术语"},
                    "top_k": {"type": "integer", "description": "返回条数，1-8，默认 5"},
                },
                "required": ["query"],
            },
            roles=ALL_ROLES,
            risk=RISK_READ,
            handler=_search_knowledge,
        ),
        ToolSpec(
            name="search_resources",
            label="查找资料",
            description=(
                "按关键词查找知识库中可打开的具体文档或视频，返回带跳转链接的资料卡片。"
                "当用户说“帮我找/有没有/推荐 XX 课件、讲义、视频、习题”时使用。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "资料关键词，如“ESP32 I2C 课件”"},
                },
                "required": ["query"],
            },
            roles=ALL_ROLES,
            risk=RISK_READ,
            handler=_search_resources,
        ),
        ToolSpec(
            name="get_document_detail",
            label="查看文档详情",
            description="按文档 ID 查看标题、分类、标签、页数与原文链接。通常先用 search_resources 拿到 ID。",
            parameters={
                "type": "object",
                "properties": {
                    "document_id": {"type": "integer", "description": "文档 ID"},
                },
                "required": ["document_id"],
            },
            roles=ALL_ROLES,
            risk=RISK_READ,
            handler=_get_document_detail,
        ),
        ToolSpec(
            name="list_my_collections",
            label="查询我的补采",
            description="查看当前用户提交过的补采需求及处理状态。用户问“我提交的补采进度/有没有补上”时使用。",
            parameters={
                "type": "object",
                "properties": {
                    "status": {
                        "type": "integer",
                        "description": "可选：0待处理 1已触发 2已完成 3已忽略 4未匹配",
                        "enum": [0, 1, 2, 3, 4],
                    },
                },
                "required": [],
            },
            roles=ALL_ROLES,
            risk=RISK_READ,
            handler=_list_my_collections,
        ),
        ToolSpec(
            name="list_my_tickets",
            label="查询我的工单",
            description="查看当前用户提交过的工单、处理状态与老师回复。用户问“我的工单/反馈进度”时使用。",
            parameters={
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "description": "可选：pending/processing/resolved/closed",
                        "enum": ["pending", "processing", "resolved", "closed"],
                    },
                },
                "required": [],
            },
            roles=ALL_ROLES,
            risk=RISK_READ,
            handler=_list_my_tickets,
        ),
        ToolSpec(
            name="list_notifications",
            label="查询通知",
            description="查看当前用户的站内通知（默认未读）。用户问“有没有新通知/审核结果/补采结果”时使用。",
            parameters={
                "type": "object",
                "properties": {
                    "unread_only": {"type": "boolean", "description": "是否只看未读，默认 true"},
                },
                "required": [],
            },
            roles=ALL_ROLES,
            risk=RISK_READ,
            handler=_list_notifications,
        ),
        ToolSpec(
            name="list_my_classes",
            label="查询我的班级",
            description="教师查看自己任教的班级，管理员查看全部班级。用户问“我教哪些班/班级情况”时使用。",
            parameters={"type": "object", "properties": {}, "required": []},
            roles=TEACHER_VIEW_ROLES,
            risk=RISK_READ,
            handler=_list_my_classes,
        ),
        ToolSpec(
            name="class_students",
            label="查询班级学生",
            description="查看某个班级的学生名单与学习概况（提问次数、最近提问时间）。教师只能查本人任教的班级。",
            parameters={
                "type": "object",
                "properties": {
                    "class_id": {"type": "integer", "description": "班级 ID，先通过 list_my_classes 获取"},
                },
                "required": ["class_id"],
            },
            roles=TEACHER_VIEW_ROLES,
            risk=RISK_READ,
            handler=_class_students,
        ),
        ToolSpec(
            name="class_question_hotspots",
            label="班级提问热点",
            description=(
                "查看某个班级近 N 天学生提问的高频关键词、参与人数与代表问题。"
                "教师问“我班最近都在问什么/哪些知识点问题多”时使用。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "class_id": {"type": "integer", "description": "班级 ID，先通过 list_my_classes 获取"},
                    "days": {"type": "integer", "description": "统计最近几天，默认 7"},
                    "top_n": {"type": "integer", "description": "返回关键词数量，默认 10"},
                },
                "required": ["class_id"],
            },
            roles=TEACHER_VIEW_ROLES,
            risk=RISK_READ,
            handler=_class_question_hotspots,
        ),
        ToolSpec(
            name="class_unanswered_questions",
            label="班级未解答问题",
            description=(
                "查看某个班级近 N 天知识库未能回答（拒答）的问题，用于发现知识缺口。"
                "教师问“我班哪些问题系统答不上来/该补什么资料”时使用。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "class_id": {"type": "integer", "description": "班级 ID"},
                    "days": {"type": "integer", "description": "统计最近几天，默认 7"},
                    "limit": {"type": "integer", "description": "返回条数，默认 10"},
                },
                "required": ["class_id"],
            },
            roles=TEACHER_VIEW_ROLES,
            risk=RISK_READ,
            handler=_class_unanswered_questions,
        ),
        ToolSpec(
            name="student_learning_profile",
            label="学生学习画像",
            description=(
                "查看某名学生在班级内的学习情况：累计提问、近期提问、未命中次数与最近问题。"
                "教师问“某某最近学得怎么样/活跃吗”时使用，需先通过 class_students 拿到学生 ID。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "class_id": {"type": "integer", "description": "班级 ID"},
                    "student_id": {"type": "integer", "description": "学生用户 ID"},
                    "days": {"type": "integer", "description": "近期窗口天数，默认 7"},
                },
                "required": ["class_id", "student_id"],
            },
            roles=TEACHER_VIEW_ROLES,
            risk=RISK_READ,
            handler=_student_learning_profile,
        ),
        ToolSpec(
            name="class_teaching_report",
            label="班级学情周报",
            description=(
                "生成某班级近 N 天的学情汇总：参与人数、提问量、未命中次数、热点关键词与待补充问题。"
                "教师问“帮我生成本周班级学情/教学周报”时使用。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "class_id": {"type": "integer", "description": "班级 ID"},
                    "days": {"type": "integer", "description": "统计周期天数，默认 7"},
                },
                "required": ["class_id"],
            },
            roles=TEACHER_VIEW_ROLES,
            risk=RISK_READ,
            handler=_class_teaching_report,
        ),
        ToolSpec(
            name="get_admin_overview",
            label="查看待办概览",
            description=(
                "管理员查看待办概览：待审核文档数、待处理补采需求数、待处理工单数。"
                "用户问“今天有什么要处理/待审核多少/运营情况”时使用。"
            ),
            parameters={"type": "object", "properties": {}, "required": []},
            roles=ADMIN_ROLES,
            risk=RISK_READ,
            handler=_get_admin_overview,
        ),
        ToolSpec(
            name="list_pending_documents",
            label="待审核文档",
            description=(
                "列出待审核文档及等待天数，可按分类筛选。"
                "管理员问“有哪些文档待审核/审核积压多久”时使用。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "返回条数，默认 10"},
                    "category_id": {"type": "integer", "description": "可选：按分类 ID 筛选"},
                },
                "required": [],
            },
            roles=ADMIN_ROLES,
            risk=RISK_READ,
            handler=_list_pending_documents,
        ),
        ToolSpec(
            name="list_pending_work",
            label="待处理积压",
            description=(
                "查看待处理补采需求与工单队列，含最长等待天数。"
                "管理员问“补采和工单积压多少/谁还没处理”时使用。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "每类返回条数，默认 10"},
                },
                "required": [],
            },
            roles=ADMIN_ROLES,
            risk=RISK_READ,
            handler=_list_pending_work,
        ),
        ToolSpec(
            name="knowledge_gap_report",
            label="知识缺口报告",
            description=(
                "统计近 N 天知识库未命中的问题并按提问次数排序，用于确定补采优先级。"
                "管理员问“最近大家问不到什么/该补充哪些资料”时使用。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "统计最近几天，默认 7"},
                    "limit": {"type": "integer", "description": "返回问题条数，默认 10"},
                },
                "required": [],
            },
            roles=ADMIN_ROLES,
            risk=RISK_READ,
            handler=_knowledge_gap_report,
        ),
        ToolSpec(
            name="platform_usage_stats",
            label="平台使用统计",
            description=(
                "查看近 N 天提问量、活跃用户数、已解答率、每日趋势与被引用最多的资料。"
                "管理员问“这周使用情况/活跃度怎么样”时使用。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "统计最近几天，默认 7"},
                },
                "required": [],
            },
            roles=ADMIN_ROLES,
            risk=RISK_READ,
            handler=_platform_usage_stats,
        ),
        ToolSpec(
            name="account_overview",
            label="账号概览",
            description=(
                "查看账号总数、角色分布、启停状态、班级数量与近期登录人数。"
                "管理员问“有多少师生账号/活跃情况”时使用。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "登录统计窗口天数，默认 30"},
                },
                "required": [],
            },
            roles=ADMIN_ROLES,
            risk=RISK_READ,
            handler=_account_overview,
        ),
        ToolSpec(
            name="audit_summary",
            label="审计摘要",
            description=(
                "汇总近 N 天审计日志：关键操作分布、被拦截次数、敏感词命中次数。"
                "管理员问“有没有异常操作/安全情况”时使用。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "统计最近几天，默认 7"},
                    "limit": {"type": "integer", "description": "返回操作类型条数，默认 10"},
                },
                "required": [],
            },
            roles=ADMIN_ROLES,
            risk=RISK_READ,
            handler=_audit_summary,
        ),
        ToolSpec(
            name="submit_collection_request",
            label="提交补采需求",
            description=(
                "把知识库没有覆盖的问题提交为补采需求，驱动爬虫定向采集。"
                "属于写操作，系统会先向用户展示确认卡片，用户确认后才真正提交。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "需要补采的完整问题"},
                    "reason": {
                        "type": "string",
                        "description": "missed=知识库未命中，negative_feedback=对回答不满意",
                        "enum": ["missed", "negative_feedback"],
                    },
                    "note": {"type": "string", "description": "补充说明（可选）"},
                },
                "required": ["question"],
            },
            roles=ALL_ROLES,
            risk=RISK_WRITE,
            handler=_submit_collection_request,
        ),
        ToolSpec(
            name="create_ticket",
            label="提交工单",
            description=(
                "把需要人工处理的问题转成工单，交给老师/管理员跟进。"
                "属于写操作，系统会先向用户展示确认卡片，用户确认后才真正创建。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "工单标题，简短概括问题"},
                    "question": {"type": "string", "description": "用户的完整问题"},
                    "detail": {"type": "string", "description": "补充说明（可选）"},
                    "priority": {
                        "type": "string",
                        "description": "优先级，默认 medium",
                        "enum": ["high", "medium", "low"],
                    },
                },
                "required": ["title", "question"],
            },
            roles=ALL_ROLES,
            risk=RISK_WRITE,
            handler=_create_ticket,
        ),
    ]

    for spec in specs:
        registry.register(spec)
