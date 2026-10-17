"""sitemap.xml 整站采集适配器：拉 sitemap → 过滤路径前缀 → 逐页抓取。

适用于提供 sitemap 的官方站点（如 espressif.com.cn），无需解析列表页结构。
"""
from __future__ import annotations

import logging

import httpx
from lxml import html as lxml_html

from ...settings import get_settings
from ..politeness import wait_before_request
from .base import RawItem
from .known import is_known, page_title

log = logging.getLogger(__name__)


def fetch(site, http: httpx.Client) -> list[RawItem]:
    cfg = getattr(site, "config_json", None) or getattr(site, "config", None) or {}
    sitemap_url = cfg.get("sitemap_url") or ""
    if not sitemap_url:
        log.warning("站点 %s 未配置 sitemap_url，跳过", site.code)
        return []
    path_prefix = cfg.get("path_prefix") or ""
    max_items = int(cfg.get("max_items", 20))
    site_ua = cfg.get("user_agent") or ""
    settings = get_settings()

    def get(url: str) -> httpx.Response:
        kwargs = {"timeout": settings.crawl_timeout_seconds}
        if site_ua:
            kwargs["headers"] = {"User-Agent": site_ua}
        return http.get(url, **kwargs)

    # 1. sitemap.xml → URL 列表
    wait_before_request(site.code, site.rate_limit)
    resp = get(sitemap_url)
    resp.raise_for_status()
    doc = lxml_html.fromstring(resp.content)  # sitemap 为 XML，直接用 lxml 解析
    urls: list[str] = []
    for loc in doc.cssselect("loc"):
        u = (loc.text or "").strip()
        if not u:
            continue
        if path_prefix and path_prefix not in u:
            continue
        if is_known(u):
            continue
        urls.append(u)
    if not urls:
        log.warning("站点 %s 的 sitemap 无匹配 URL（前缀 %s），跳过", site.code, path_prefix)
        return []

    # 2. 逐页抓取详情（HTML 页才入库，PDF 附件交给 OCR 链路后续处理）
    items: list[RawItem] = []
    for url in urls:
        if len(items) >= max_items:
            break
        wait_before_request(site.code, site.rate_limit)
        try:
            page = get(url)
            page.raise_for_status()
        except Exception as exc:  # noqa: BLE001 - 单页失败不影响整体
            log.warning("sitemap 页面抓取失败 %s: %s", url, exc)
            continue
        content_type = page.headers.get("content-type", "")
        if "text/html" not in content_type:
            continue  # PDF 等附件不在本适配器处理范围
        items.append(RawItem(
            url=str(page.url),
            title=page_title(page.text)[:500],
            content_html=page.text,
        ))
    log.info("站点 %s：sitemap 匹配 %d 个 URL，本轮抓取 %d 篇", site.code, len(urls), len(items))
    return items
