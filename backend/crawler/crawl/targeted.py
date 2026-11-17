"""发现式补采的定向抓取：消费 discovery_queue 中排队的候选 URL。

与站点遍历（crawl.py）的区别：
- URL 来自 scout Agent 的站内检索结果，逐个抓单页，不遍历站点；
- 未备案域名一律按 medium 版权等级入库（仅节选前 500 字 + 原文链接）；
- 抓取前检查 robots.txt，并按域名复用限速/熔断状态。
"""
from __future__ import annotations

import logging
import re
import time
from urllib.parse import urlsplit

import httpx

from ..settings import get_settings
from ..store.db import session_scope
from ..store.models import DiscoveryQueue, Site, SourceAuthorization
from ..timeutil import utcnow
from . import robots
from .adapters.base import RawItem
from .adapters.known import page_title
from .crawl import ingest_item
from .dedup import url_hash
from .politeness import is_circuit_open, record_site_failure, record_site_success, wait_before_request
from ..store import repo

log = logging.getLogger(__name__)

# 官方/公开文档站：全文入库；其余发现式来源按 medium 处理
_FULLTEXT_HOSTS = {
    "docs.espressif.com", "github.com", "www.raspberrypi.com",
    # 补采种子源（官方入门教程）
    "dev.java", "docs.oracle.com", "docs.python.org",
    "zh.cppreference.com", "oi-wiki.org", "spring.io",
    "docs.spring.io", "dev.mysql.com",
}


class TargetedStats:
    def __init__(self) -> None:
        self.fetched = 0
        self.new_docs = 0
        self.failed = 0
        self.skipped = 0


def run_targeted(limit: int = 8) -> TargetedStats:
    """抓取队列中分数最高的 limit 个候选 URL。"""
    stats = TargetedStats()
    settings = get_settings()
    with httpx.Client(
        headers={"User-Agent": settings.crawl_user_agent},
        timeout=settings.crawl_timeout_seconds,
        follow_redirects=True,
    ) as http:
        with session_scope() as session:
            rows = (
                session.query(DiscoveryQueue)
                .filter(DiscoveryQueue.status == "queued")
                .order_by(DiscoveryQueue.score.desc(), DiscoveryQueue.id)
                .limit(limit)
                .all()
            )
            for row in rows:
                _fetch_one(session, http, row, stats)
    log.info(
        "定向抓取完成：抓取 %d，新增 %d，失败 %d，跳过 %d",
        stats.fetched, stats.new_docs, stats.failed, stats.skipped,
    )
    return stats


def _fetch_one(session, http: httpx.Client, row: DiscoveryQueue, stats: TargetedStats) -> None:
    if not robots.is_allowed(http, row.url):
        row.status = "skipped"
        row.error = "robots.txt 禁止抓取"
        row.fetched_at = utcnow()
        stats.skipped += 1
        return

    site = _ensure_site(session, row.url)
    if is_circuit_open(site):
        row.status = "skipped"
        row.error = "域名熔断中"
        row.fetched_at = utcnow()
        stats.skipped += 1
        return

    try:
        wait_before_request(site.code, site.rate_limit)
        # GitHub 国内访问不稳定：单页给更长超时并重试一次，避免刚失败两次就熔断 6 小时
        is_github = "github.com" in row.url
        attempts = 2 if is_github else 1
        last_exc: Exception | None = None
        for attempt in range(attempts):
            try:
                resp = http.get(row.url, timeout=60.0) if is_github else http.get(row.url)
                resp.raise_for_status()
                last_exc = None
                break
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if attempt + 1 < attempts:
                    time.sleep(2)
        if last_exc is not None:
            raise last_exc
    except Exception as exc:  # noqa: BLE001 - 单条失败不影响队列其余条目
        record_site_failure(site)
        row.status = "failed"
        row.error = f"{type(exc).__name__}: {exc}"[:500]
        row.fetched_at = utcnow()
        stats.failed += 1
        log.warning("定向抓取失败 %s: %s", row.url, exc)
        return
    record_site_success(site)

    item = RawItem(
        url=str(resp.url),
        title=page_title(resp.text) or row.title,
        content_html=resp.text,
    )
    try:
        doc = ingest_item(session, site, item)
        session.flush()
        if doc is None:  # URL/内容重复：复用已有文档，保证需求仍能闭环
            doc = repo.find_document_by_url_hash(session, url_hash(item.url))
        elif not (doc.text or "").strip():
            # 正文抽取失败（只剩标题）不能算补采成功，避免把空文档写进知识库
            session.delete(doc)
            row.status = "skipped"
            row.error = "正文抽取为空"
            row.fetched_at = utcnow()
            stats.skipped += 1
            return
    except Exception as exc:  # noqa: BLE001
        row.status = "failed"
        row.error = f"{type(exc).__name__}: {exc}"[:500]
        row.fetched_at = utcnow()
        stats.failed += 1
        log.warning("定向入库失败 %s: %s", row.url, exc)
        return

    row.status = "fetched"
    row.fetched_at = utcnow()
    stats.fetched += 1
    if doc is not None:
        row.doc_id = doc.id
        stats.new_docs += 1


def _ensure_site(session, url: str) -> Site:
    """按域名生成站点档案（enabled=False，不参与每日站点遍历）。"""
    host = (urlsplit(url).hostname or "unknown").lower()
    code = "scout_" + re.sub(r"[^a-z0-9]+", "_", host)[:40]
    site = session.query(Site).filter(Site.code == code).one_or_none()
    if site is not None:
        return site

    risk = "low" if host in _FULLTEXT_HOSTS else "medium"
    site = Site(
        code=code,
        name=f"发现式来源 {host}",
        source_type="html",
        adapter="url_list",
        base_url=f"https://{host}",
        risk_level=risk,
        authority_weight=0.8,
        rate_limit=5.0,
        enabled=False,
        license_note="发现式采集：按补采问题检索到的外部页面；未备案域名仅存节选与原文链接，仅校内教学使用",
    )
    session.add(site)
    session.flush()
    session.add(SourceAuthorization(
        site_id=site.id,
        auth_type="发现式采集",
        scope="校内教学，不对外分发",
        note="由补采侦察 Agent 自动发现；未备案来源仅保留节选与原文链接",
    ))
    return site
