"""仓储层：站点档案 / 文档去重 / 同步留痕 / LLM 账本的常用读写。

约定：本模块只做数据访问，不含业务规则（业务在 crawl/sync/agents 各层）。
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..settings import SiteConfig
from ..timeutil import utcnow
from .models import (
    CrawlTask,
    Document,
    KnowledgeBaseSync,
    LlmUsage,
    Site,
    SourceAuthorization,
)

# ---------------------------------------------------------------- 站点


def sync_sites(session: Session, sites: list[SiteConfig] | None = None) -> int:
    """把 config/sites.yaml 同步进 sites 表（按 code 幂等 upsert），返回同步数。"""
    from ..settings import load_sites

    configs = sites if sites is not None else load_sites()
    for sc in configs:
        site = session.query(Site).filter(Site.code == sc.code).one_or_none()
        if site is None:
            site = Site(code=sc.code)
            session.add(site)
        site.name = sc.name
        site.source_type = sc.source_type
        site.adapter = sc.adapter
        site.base_url = sc.base_url
        site.risk_level = sc.risk_level
        site.authority_weight = sc.authority_weight
        site.rate_limit = sc.rate_limit
        site.license_note = sc.license_note
        site.enabled = sc.enabled
        site.config_json = sc.config
        # 首次入库时补一条版权合规留痕
        if site.id is None:
            session.flush()
            session.add(SourceAuthorization(
                site_id=site.id,
                auth_type=_auth_type_for(sc),
                note=sc.license_note or "站点档案默认声明",
            ))
    return len(configs)


def _auth_type_for(sc: SiteConfig) -> str:
    if sc.source_type in ("rss", "api"):
        return "官方API/RSS公开"
    return "站点档案声明"


# ---------------------------------------------------------------- 文档去重与查询


def find_document_by_url_hash(session: Session, url_hash: str) -> Document | None:
    return session.query(Document).filter(Document.url_hash == url_hash).first()


def find_document_by_content_hash(session: Session, content_hash: str) -> Document | None:
    return session.query(Document).filter(Document.content_hash == content_hash).first()


def find_near_dup(
    session: Session,
    simhash: str,
    window_days: int = 3,
    hamming_threshold: int = 3,
) -> Document | None:
    """在近 N 天窗口内找 SimHash 近重复文档（跨源转载检测）。"""
    from ..crawl.dedup import hamming_distance

    since = utcnow() - timedelta(days=window_days)
    rows = (
        session.query(Document.id, Document.simhash)
        .filter(Document.simhash.isnot(None), Document.fetched_at >= since)
        .all()
    )
    for doc_id, other in rows:
        if hamming_distance(simhash, other) <= hamming_threshold:
            return session.get(Document, doc_id)
    return None


def get_document(session: Session, doc_id: int) -> Document | None:
    return (
        session.query(Document)
        .options(selectinload(Document.site))
        .filter(Document.id == doc_id)
        .one_or_none()
    )


# ---------------------------------------------------------------- 智能体流水线查询


def untagged_documents(session: Session, limit: int = 500) -> list[Document]:
    return (
        session.query(Document)
        .filter(Document.is_tagged.is_(False))
        .order_by(Document.id)
        .limit(limit)
        .all()
    )


def unreviewed_documents(session: Session, limit: int = 500) -> list[Document]:
    return (
        session.query(Document)
        .filter(Document.is_reviewed.is_(False))
        .order_by(Document.id)
        .limit(limit)
        .all()
    )


def unsummarized_documents(session: Session, limit: int = 500) -> list[Document]:
    """待摘要文档：已审核通过且有实质正文的文档才值得摘要。"""
    return (
        session.query(Document)
        .filter(Document.is_summarized.is_(False), Document.review_pass.is_(True))
        .order_by(Document.id)
        .limit(limit)
        .all()
    )


# ---------------------------------------------------------------- 知识库同步


def unsynced_documents(session: Session, limit: int = 100) -> list[Document]:
    """尚未同步到知识库主库的文档，按 id 升序取前 N 篇（含站点信息）。"""
    synced = select(KnowledgeBaseSync.doc_id)
    return (
        session.query(Document)
        .options(selectinload(Document.site))
        .filter(~Document.id.in_(synced))
        .order_by(Document.id)
        .limit(limit)
        .all()
    )


def mark_kb_synced(
    session: Session,
    *,
    doc_id: int,
    kb_doc_id: int | None = None,
    title: str = "",
    status: str = "ok",
    error: str = "",
) -> None:
    """记录一篇文档已同步到知识库（幂等，按 doc_id 唯一索引）。"""
    session.add(KnowledgeBaseSync(
        doc_id=doc_id, kb_doc_id=kb_doc_id, title=title[:512],
        status=status, error=error[:1000],
    ))


# ---------------------------------------------------------------- LLM 账本


def record_usage(
    session: Session,
    *,
    task: str,
    provider: str = "dashscope",
    model: str = "",
    batch: bool = False,
    tokens_in: int = 0,
    tokens_out: int = 0,
    cost_est: float = 0.0,
    latency_ms: int = 0,
    status: str = "ok",
) -> None:
    session.add(LlmUsage(
        task=task,
        provider=provider,
        model=model,
        batch=batch,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_est=cost_est,
        latency_ms=latency_ms,
        status=status,
    ))


def daily_cost(session: Session, day: date | None = None) -> float:
    day = day or date.today()
    start = datetime.combine(day, time.min)
    end = datetime.combine(day + timedelta(days=1), time.min)
    value = (
        session.query(func.coalesce(func.sum(LlmUsage.cost_est), 0.0))
        .filter(LlmUsage.created_at >= start, LlmUsage.created_at < end)
        .scalar()
    )
    return float(value or 0.0)


# ---------------------------------------------------------------- 统计


def stats_snapshot(session: Session) -> dict:
    doc_count = session.query(func.count(Document.id)).scalar() or 0
    site_count = session.query(func.count(Site.id)).scalar() or 0
    synced_count = session.query(func.count(KnowledgeBaseSync.id)).scalar() or 0
    return {
        "documents": int(doc_count),
        "sites": int(site_count),
        "kb_synced": int(synced_count),
        "today_cost": daily_cost(session),
    }


def site_status(session: Session) -> list[dict]:
    """站点状态：档案 + 最近一次采集结果 + 该站文档数。"""
    sites = session.query(Site).order_by(Site.id).all()
    result = []
    for site in sites:
        doc_count = (
            session.query(func.count(Document.id)).filter(Document.site_id == site.id).scalar() or 0
        )
        last_task = (
            session.query(CrawlTask)
            .filter(CrawlTask.site_id == site.id)
            .order_by(CrawlTask.id.desc())
            .first()
        )
        result.append({
            "code": site.code,
            "name": site.name,
            "enabled": site.enabled,
            "risk_level": site.risk_level,
            "doc_count": int(doc_count),
            "last_status": last_task.status if last_task else "未采集",
            "last_time": last_task.started_at if last_task else None,
            "breaker_until": site.breaker_until,
        })
    return result
