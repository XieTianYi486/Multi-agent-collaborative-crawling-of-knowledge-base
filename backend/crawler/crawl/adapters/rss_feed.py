"""通用 RSS/Atom 适配器：feedparser 拉取。

RSS 是增量采集第一优先级：零页面请求、无反爬风险、天然结构化。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import feedparser
import httpx

from ...settings import get_settings
from .base import RawItem

log = logging.getLogger(__name__)


def _entry_datetime(entry) -> datetime | None:
    for attr in ("published_parsed", "updated_parsed"):
        value = getattr(entry, attr, None)
        if value:
            # feedparser 返回 UTC 结构体；统一存 naive UTC（与 fetched_at 一致）
            return datetime(*value[:6], tzinfo=timezone.utc).replace(tzinfo=None)
    return None


def fetch(site, http: httpx.Client) -> list[RawItem]:
    cfg = getattr(site, "config_json", None) or getattr(site, "config", None) or {}
    feed_url = cfg.get("feed_url") or ""
    if not feed_url:
        log.warning("站点 %s 未配置 feed_url，跳过", site.code)
        return []
    settings = get_settings()
    resp = http.get(feed_url, timeout=settings.crawl_timeout_seconds)
    resp.raise_for_status()
    feed = feedparser.parse(resp.content)
    items: list[RawItem] = []
    for entry in feed.entries:
        link = (getattr(entry, "link", "") or "").strip()
        if not link:
            continue
        content = None
        if entry.get("content"):
            content = entry.content[0].get("value", "")
        summary = (getattr(entry, "summary", "") or "").strip()
        items.append(RawItem(
            url=link,
            title=(getattr(entry, "title", "") or "").strip(),
            content_html=content or summary or None,
            published_at=_entry_datetime(entry),
            author=(getattr(entry, "author", "") or "").strip(),
            meta={"tags": [t.get("term", "") for t in getattr(entry, "tags", [])]},
        ))
    return items
