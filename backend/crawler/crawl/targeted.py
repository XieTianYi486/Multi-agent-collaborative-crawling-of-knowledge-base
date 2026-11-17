"""发现式补采的定向抓取：消费 discovery_queue 中排队的候选 URL。

与站点遍历（crawl.py）的区别：
- URL 来自 scout Agent 的站内检索结果，逐个抓单页，不遍历站点；
- 未备案域名一律按 medium 版权等级入库（仅节选前 500 字 + 原文链接）；
- 抓取前检查 robots.txt，并按域名复用限速/熔断状态。
"""
from __future__ import annotations

import ipaddress
import logging
import re
import socket
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


def run_targeted(
    limit: int = 8,
    open_request_ids: Optional[list[int]] = None,
) -> TargetedStats:
    """
    抓取队列中分数最高的 limit 个候选 URL。

    open_request_ids：仍处于开放状态（status=1）的补采需求。
    仅这些需求的历史失败候选允许复活重试——已关闭需求不再浪费抓取额度，
    避免"上一轮失败的 URL 永久死路"与"已忽略需求还占额度"两个极端。
    """
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
            if len(rows) < limit and open_request_ids:
                # 新鲜队列不足时，复活开放需求上一轮的失败候选（transient 故障重试）
                remaining = limit - len(rows)
                failed = (
                    session.query(DiscoveryQueue)
                    .filter(
                        DiscoveryQueue.status == "failed",
                        DiscoveryQueue.request_id.in_(open_request_ids),
                    )
                    .order_by(DiscoveryQueue.score.desc(), DiscoveryQueue.id)
                    .limit(remaining)
                    .all()
                )
                for row in failed:
                    row.status = "queued"
                    row.error = None
                    row.fetched_at = None
                    rows.append(row)
                session.flush()
            for row in rows:
                _fetch_one(session, http, row, stats)
    log.info(
        "定向抓取完成：抓取 %d，新增 %d，失败 %d，跳过 %d",
        stats.fetched, stats.new_docs, stats.failed, stats.skipped,
    )
    return stats


def _fetch_one(session, http: httpx.Client, row: DiscoveryQueue, stats: TargetedStats) -> None:
    def _skip(reason: str) -> None:
        row.status = "skipped"
        row.error = reason
        row.fetched_at = utcnow()
        stats.skipped += 1

    # 公网地址校验先于 robots：内网/云元数据地址连 robots.txt 请求都不应发出
    host = urlsplit(row.url).hostname or ""
    if not _is_public_host(host):
        _skip("目标地址不是公网地址（防内网/云元数据探测）")
        return

    if not robots.is_allowed(http, row.url):
        _skip("robots.txt 禁止抓取")
        return

    site = _ensure_site(session, row.url)
    if is_circuit_open(site):
        _skip("域名熔断中")
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

    # 重定向后复检：目的地换主机时重新校验公网地址、robots 与站点归属，
    # 防止低风险源跳转到内网地址或未经授权的高风险站点
    final_host = urlsplit(str(resp.url)).hostname or ""
    if final_host and final_host != host:
        if not _is_public_host(final_host):
            _skip("重定向到非公网地址，已拦截")
            return
        if not robots.is_allowed(http, str(resp.url)):
            _skip("重定向目标被 robots.txt 禁止")
            return
        site = _ensure_site(session, str(resp.url))

    item = RawItem(
        url=str(resp.url),
        title=page_title(resp.text) or row.title,
        content_html=resp.text,
    )
    try:
        # return_existing=True：URL/内容哈希/SimHash 重复时返回库中已有文档，
        # 让队列行关联到既有文档——补采需求靠 kb_syncs 闭环，重复内容同样算覆盖
        doc = ingest_item(session, site, item, return_existing=True)
        session.flush()
        if doc is None:
            # 无实质内容：不入库
            row.status = "skipped"
            row.error = "无实质内容"
            row.fetched_at = utcnow()
            stats.skipped += 1
            return
        if not (doc.text or "").strip():
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
    row.doc_id = doc.id
    # 只有本轮新建的文档计入新增（doc in session.new 表示尚未持久化的新对象）
    if doc in session.new:
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


def _is_public_host(host: str) -> bool:
    """解析主机名并确认全部地址都是公网地址（防 SSRF / 内网 / 云元数据探测）。

    ipaddress.is_global 会把回环、私网（10/8、172.16/12、192.168/16）、
    链路本地（169.254/16）、保留段全部判为非公网。解析失败按不安全处理。
    """
    if not host:
        return False
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    if not infos:
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False
        if not ip.is_global:
            return False
    return True
