# ============================================================
# 爬取中心接口
# 多智能体爬取流水线的管理面板：站点状态 / 采集统计 /
# LLM 成本账本 / 入库同步记录 / 手动触发流水线
# ============================================================

import logging
from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func

from app.api.deps import require_knowledge_admin
from app.schemas.common import APIResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/crawler", tags=["爬取中心"])


def _iso(dt) -> str:
    """datetime → ISO 字符串（FastAPI 序列化安全）"""
    return dt.isoformat() if dt else None


# ==================== 总览 ====================


def _kb_stats() -> dict:
    """知识库主库总量（与爬取子库口径分离）。

    批量导入 / 人工上传的文档不经爬取流水线，只落在知识库主库，
    因此单独聚合后一并返回，避免与爬取子库的账混在一起。
    """
    from app.db.sqlite import SessionLocal
    from app.models.document import Category, DocChunk
    from app.models.document import Document as KbDocument

    day_start = datetime.combine(date.today(), time.min)
    db = SessionLocal()
    try:
        return {
            "documents": db.query(func.count(KbDocument.id)).scalar() or 0,
            "published": db.query(func.count(KbDocument.id))
            .filter(KbDocument.status == 1).scalar() or 0,
            "chunks": db.query(func.count(DocChunk.id)).scalar() or 0,
            "with_source_url": db.query(func.count(KbDocument.id))
            .filter(KbDocument.source_url.isnot(None), KbDocument.source_url != "")
            .scalar() or 0,
            "categories": db.query(func.count(Category.id)).scalar() or 0,
            "documents_today": db.query(func.count(KbDocument.id))
            .filter(KbDocument.created_at >= day_start).scalar() or 0,
            # 按导入日期聚合的批次明细（最近若干批，倒序）
            "batches": [
                {"date": str(d), "count": c}
                for d, c in db.query(
                    func.date(KbDocument.created_at), func.count(KbDocument.id)
                ).group_by(func.date(KbDocument.created_at))
                .order_by(func.date(KbDocument.created_at).desc())
                .limit(6).all()
            ],
        }
    finally:
        db.close()


@router.get("/overview", response_model=APIResponse)
def crawler_overview(
    _user=Depends(require_knowledge_admin),
):
    """爬取中心总览：文档/同步/成本/运行状态一站式汇总。

    stats 为爬取子库口径；kb 为知识库主库口径（含批量导入文档）。
    """
    from crawler import runner
    from crawler.store import repo
    from crawler.store.db import session_scope
    from crawler.store.models import Document, KnowledgeBaseSync, LlmUsage, Site

    with session_scope() as s:
        today = date.today()
        day_start = datetime.combine(today, time.min)
        day_end = datetime.combine(today + timedelta(days=1), time.min)
        stats = {
            "sites": s.query(func.count(Site.id)).scalar() or 0,
            "sites_enabled": s.query(func.count(Site.id)).filter(Site.enabled.is_(True)).scalar() or 0,
            "documents": s.query(func.count(Document.id)).scalar() or 0,
            "documents_today": s.query(func.count(Document.id))
            .filter(Document.fetched_at >= day_start, Document.fetched_at < day_end).scalar() or 0,
            "kb_synced": s.query(func.count(KnowledgeBaseSync.id)).scalar() or 0,
            "kb_sync_ok": s.query(func.count(KnowledgeBaseSync.id))
            .filter(KnowledgeBaseSync.status == "ok").scalar() or 0,
            "kb_sync_failed": s.query(func.count(KnowledgeBaseSync.id))
            .filter(KnowledgeBaseSync.status == "failed").scalar() or 0,
            "llm_cost_today": repo.daily_cost(s, today),
            "llm_calls": s.query(func.count(LlmUsage.id)).scalar() or 0,
        }
    run = runner.get_run_state()
    return APIResponse(data={
        "stats": stats,
        "kb": _kb_stats(),
        "run": _run_state_dict(run),
    })


def _run_state_dict(run: dict) -> dict:
    return {
        "running": run["running"],
        "trigger": run["trigger"],
        "started_at": _iso(run["started_at"]),
        "finished_at": _iso(run["finished_at"]),
        "error": run["error"],
        "step_results": {
            name: {
                "ok": r["ok"],
                "skipped": r["skipped"],
                "error": r["error"],
                "duration_ms": r["duration_ms"],
            }
            for name, r in run["step_results"].items()
        },
    }


# ==================== 站点状态 ====================


@router.get("/sites", response_model=APIResponse)
def crawler_sites(
    _user=Depends(require_knowledge_admin),
):
    """站点档案与最近采集结果。"""
    from crawler.store import repo
    from crawler.store.db import session_scope

    with session_scope() as s:
        rows = repo.site_status(s)
    for r in rows:
        r["last_time"] = _iso(r["last_time"])
        r["breaker_until"] = _iso(r["breaker_until"])
    return APIResponse(data=rows)


# ==================== 入库同步记录 ====================


@router.get("/syncs", response_model=APIResponse)
def crawler_syncs(
    limit: int = Query(20, ge=1, le=100),
    status_filter: str = Query("", alias="status"),
    _user=Depends(require_knowledge_admin),
):
    """最近入库同步记录（可选按 status 过滤：ok/failed/skipped）。"""
    from crawler.store.db import session_scope
    from crawler.store.models import KnowledgeBaseSync

    with session_scope() as s:
        query = s.query(KnowledgeBaseSync).order_by(KnowledgeBaseSync.id.desc())
        if status_filter:
            query = query.filter(KnowledgeBaseSync.status == status_filter)
        rows = query.limit(limit).all()
        kb_titles = {}
        if rows:
            from app.db.sqlite import SessionLocal
            from app.models.document import Document as KbDocument

            kb_ids = [r.kb_doc_id for r in rows if r.kb_doc_id]
            if kb_ids:
                kb_db = SessionLocal()
                try:
                    for d in kb_db.query(KbDocument).filter(KbDocument.id.in_(kb_ids)).all():
                        kb_titles[d.id] = {
                            "title": d.title,
                            "status": d.status,
                            "review_status": d.review_status,
                        }
                finally:
                    kb_db.close()
        data = []
        for r in rows:
            item = {
                "doc_id": r.doc_id,
                "kb_doc_id": r.kb_doc_id,
                "title": r.title,
                "status": r.status,
                "error": r.error,
                "synced_at": _iso(r.synced_at),
                "kb_doc": kb_titles.get(r.kb_doc_id) if r.kb_doc_id else None,
            }
            data.append(item)
    return APIResponse(data=data)


# ==================== LLM 成本账本 ====================


@router.get("/usage", response_model=APIResponse)
def crawler_usage(
    _user=Depends(require_knowledge_admin),
):
    """LLM 成本账本：今日/累计成本 + 分任务明细。"""
    from crawler.store import repo
    from crawler.store.db import session_scope
    from crawler.store.models import LlmUsage

    with session_scope() as s:
        today = repo.daily_cost(s)
        total_cost = (
            s.query(func.coalesce(func.sum(LlmUsage.cost_est), 0.0)).scalar()
        )
        task_rows = (
            s.query(LlmUsage.task, LlmUsage.model,
                    func.count(LlmUsage.id), func.sum(LlmUsage.tokens_in),
                    func.sum(LlmUsage.tokens_out), func.sum(LlmUsage.cost_est))
            .group_by(LlmUsage.task, LlmUsage.model)
            .order_by(func.sum(LlmUsage.cost_est).desc())
            .all()
        )
        tasks = [
            {
                "task": t, "model": m, "calls": int(c),
                "tokens_in": int(ti or 0), "tokens_out": int(to or 0),
                "cost": round(float(co or 0.0), 6),
            }
            for t, m, c, ti, to, co in task_rows
        ]
    return APIResponse(data={
        "today_cost": today,
        "total_cost": float(total_cost or 0.0),
        "budget_daily": _budget(),
        "tasks": tasks,
    })


def _budget() -> float:
    from crawler.settings import get_settings

    return get_settings().daily_budget_cny


# ==================== 手动触发 / 运行状态 ====================


@router.post("/run", response_model=APIResponse)
def crawler_run(
    _user=Depends(require_knowledge_admin),
):
    """手动触发一次完整流水线（采集→打标→审核→摘要→入库）。

    已在运行中时返回 running=false（不重复启动）；流水线在后台线程执行，
    进度通过 GET /crawler/run 轮询。
    """
    from crawler import runner

    started = runner.start_run(trigger="manual")
    return APIResponse(data={"started": started})


@router.get("/run", response_model=APIResponse)
def crawler_run_status(
    _user=Depends(require_knowledge_admin),
):
    """当前/最近一次流水线运行状态与各步骤结果。"""
    from crawler import runner

    return APIResponse(data=_run_state_dict(runner.get_run_state()))
