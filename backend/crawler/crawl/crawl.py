"""采集入口：遍历启用站点 → 适配器拉取 → 三层去重 → 解析入库。

版权分级策略（与 config/sites.yaml risk_level 对应）：
- low          全文入库（写 Markdown 文件 + 纯文本）；
- medium       仅存节选（前 500 字）+ 原文链接，不存全文；
- high         不入库（流水线直接跳过）。
"""
from __future__ import annotations

import logging
import re

import httpx

from ..process import html2md, metadata, normalize
from ..settings import DATA_DIR, get_settings
from ..store import repo
from ..store.db import session_scope
from ..store.models import CrawlTask, Document, Site
from ..timeutil import utcnow
from .adapters import get_adapter
from .adapters.known import set_known_urls
from .dedup import content_hash, simhash64, url_hash
from .politeness import is_circuit_open, record_site_failure, record_site_success, wait_before_request

log = logging.getLogger(__name__)

_CJK_RE = re.compile(r"[一-鿿]")


class CrawlStats:
    """一次采集的统计结果。"""

    def __init__(self) -> None:
        self.new_docs = 0
        self.dup_docs = 0
        self.skipped_docs = 0
        self.failed_items = 0
        self.site_results: list[dict] = []


def run_crawl(codes: list[str] | None = None) -> CrawlStats:
    """采集所有启用站点；codes 指定时只采集对应站点（调试/测试用）。"""
    stats = CrawlStats()
    settings = get_settings()
    with httpx.Client(
        headers={"User-Agent": settings.crawl_user_agent},
        timeout=settings.crawl_timeout_seconds,
        follow_redirects=True,
    ) as http:
        with session_scope() as session:
            query = session.query(Site).filter(Site.enabled.is_(True))
            if codes:
                query = query.filter(Site.code.in_(codes))
            for site in query.order_by(Site.id).all():
                _crawl_site(session, site, http, stats)
    return stats


def _crawl_site(session, site: Site, http: httpx.Client, stats: CrawlStats) -> None:
    if is_circuit_open(site):
        log.warning("站点 %s 处于熔断期，跳过", site.code)
        stats.site_results.append({"code": site.code, "status": "breaker", "new": 0, "dup": 0})
        return
    adapter = get_adapter(site.adapter)
    if adapter is None:
        log.warning("站点 %s 缺少适配器 %s，跳过", site.code, site.adapter)
        stats.site_results.append({"code": site.code, "status": "no_adapter", "new": 0, "dup": 0})
        return
    # 高风险源不入库（版权合规），直接跳过
    if site.risk_level == "high":
        log.info("站点 %s 为高风险源（risk_level=high），跳过采集", site.code)
        stats.site_results.append({"code": site.code, "status": "high_risk_skipped", "new": 0, "dup": 0})
        return
    # 已知 URL 注入：已入库详情页不重复抓取（增量采集）
    known = {row[0] for row in session.query(Document.url).filter(Document.site_id == site.id).all()}
    set_known_urls(known)

    task = CrawlTask(site_id=site.id, started_at=utcnow())
    session.add(task)
    session.flush()

    site_new = site_dup = 0
    try:
        wait_before_request(site.code, site.rate_limit)
        items = adapter(site, http)
    except Exception as exc:  # noqa: BLE001 - 单站点失败不影响其他站点
        record_site_failure(site)
        task.status = "failed"
        task.finished_at = utcnow()
        task.error_log = f"{type(exc).__name__}: {exc}"
        log.error("站点 %s 采集失败: %s", site.code, exc)
        stats.site_results.append({"code": site.code, "status": "failed", "new": 0, "dup": 0})
        return

    for item in items:
        try:
            if _ingest_item(session, site, item):
                site_new += 1
                stats.new_docs += 1
            else:
                site_dup += 1
                stats.dup_docs += 1
        except Exception as exc:  # noqa: BLE001 - 单条失败不影响其他条目
            task.failed_items += 1
            stats.failed_items += 1
            log.warning("条目处理失败 %s: %s", item.url, exc)

    record_site_success(site)
    task.status = "ok"
    task.finished_at = utcnow()
    task.new_docs = site_new
    task.dup_docs = site_dup
    stats.site_results.append({"code": site.code, "status": "ok", "new": site_new, "dup": site_dup})
    log.info("站点 %s 完成：新增 %d，去重 %d", site.code, site_new, site_dup)


def _ingest_item(session, site: Site, item) -> bool:
    """三层去重后入库。返回是否为新增文档。"""
    settings = get_settings()

    # 1. URL 去重
    uh = url_hash(item.url)
    if repo.find_document_by_url_hash(session, uh):
        return False

    # 2. 正文抽取（HTML → Markdown + 纯文本）
    text = item.content_text or ""
    md = ""
    if item.content_html:
        md, extracted = html2md.html_to_markdown(item.content_html, item.url)
        text = extracted or text
    text = normalize.normalize_text(text)

    # 版权分级：中风险源仅存节选 + 链接，不存全文
    if site.risk_level != "low":
        text = text[:500]
        md = ""

    if not text and not item.title:
        return False  # 无实质内容，跳过

    # 3. 内容哈希去重 + SimHash 近重复
    ch = content_hash(text or item.title)
    if repo.find_document_by_content_hash(session, ch):
        return False
    sh = simhash64(text or item.title)
    if repo.find_near_dup(session, sh, settings.simhash_near_window_days, settings.simhash_hamming_threshold):
        return False

    # 落盘：Markdown（仅低风险全文）与原文 HTML
    md_rel = ""
    if md:
        md_rel = _save_data_file(f"md/{utcnow():%Y%m%d}", ch, ".md", md)
    if item.content_html and site.risk_level == "low":
        _save_data_file(f"raw/{utcnow():%Y%m%d}", ch, ".html", item.content_html)

    doc = Document(
        site_id=site.id,
        url=item.url,
        url_hash=uh,
        content_hash=ch,
        simhash=sh,
        title=item.title[:500],
        author=item.author[:250],
        published_at=item.published_at,
        lang="zh" if _CJK_RE.search(item.title + text) else "en",
        content_md_path=md_rel,
        text=text,
        license_status=site.risk_level,
        meta_json=metadata.build_meta(site, item),
    )
    session.add(doc)
    return True


def _save_data_file(subdir: str, name_hash: str, ext: str, content: str) -> str:
    """按 data/<subdir>/<hash前2位>/<hash>.<ext> 保存文件，返回相对 data/ 的路径。

    文件名全部哈希化：规避 Windows 路径长度与非法字符问题。
    """
    rel = f"{subdir}/{name_hash[:2]}/{name_hash}{ext}"
    path = DATA_DIR / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", errors="replace")
    return rel
