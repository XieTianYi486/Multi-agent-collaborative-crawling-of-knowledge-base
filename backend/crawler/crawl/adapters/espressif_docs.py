"""乐鑫文档门户适配器（documentation.espressif.com/zh/documentList）。

该页面是 Vue SPA，文档列表由 JSON API 加载，lxml 静态解析拿不到链接。
本适配器按三层策略探活，全部失败则返回空列表（站点自然跳过，符合
"爬不了就不爬"原则）：
1. 页面原始文本正则提取内嵌文档链接（SSR/初始数据场景）；
2. 候选 JSON API 端点逐个探活，从返回 JSON 递归提取文档 URL；
3. 详情页为静态 HTML，直接 httpx 抓取。
"""
from __future__ import annotations

import logging
import re

import httpx

from ...settings import get_settings
from ..politeness import wait_before_request
from .base import RawItem
from .known import is_known, page_title

log = logging.getLogger(__name__)

# 文档详情页 URL 特征（过滤 CSS/JS/图片等资源）
_DOC_URL_RE = re.compile(
    r"https?://documentation\.espressif\.com/[^\s\"'<>\\]+"
)
_ASSET_EXT_RE = re.compile(r"\.(css|js|png|jpg|jpeg|gif|svg|woff2?|ico|zip|pdf)([?#]|$)")


def fetch(site, http: httpx.Client) -> list[RawItem]:
    cfg = getattr(site, "config_json", None) or getattr(site, "config", None) or {}
    list_url = cfg.get("list_url") or "https://documentation.espressif.com/zh/documentList?eol=false"
    max_items = int(cfg.get("max_items", 40))
    settings = get_settings()

    wait_before_request(site.code, site.rate_limit)
    resp = http.get(list_url, timeout=settings.crawl_timeout_seconds)
    resp.raise_for_status()

    # 1. 页面内嵌文档链接（原始文本正则，不依赖 JS 渲染）
    urls = _extract_doc_urls(resp.text, str(resp.url))
    if not urls:
        urls = _probe_api_urls(site, http, cfg, settings)

    if not urls:
        log.warning("站点 %s 文档列表探活失败（SPA 页面 + API 端点均未取到链接），跳过",
                    site.code)
        return []

    items: list[RawItem] = []
    for url in urls:
        if len(items) >= max_items:
            break
        if is_known(url):
            continue
        wait_before_request(site.code, site.rate_limit)
        try:
            page = http.get(url, timeout=settings.crawl_timeout_seconds)
            page.raise_for_status()
        except Exception as exc:  # noqa: BLE001 - 单页失败不影响整体
            log.warning("文档详情页抓取失败 %s: %s", url, exc)
            continue
        items.append(RawItem(
            url=str(page.url),
            title=page_title(page.text)[:500],
            content_html=page.text,
        ))
    log.info("站点 %s：探得文档链接 %d 个，本轮抓取 %d 篇", site.code, len(urls), len(items))
    return items


def _extract_doc_urls(text: str, base_url: str) -> list[str]:
    """从原始文本提取文档链接（去重、去资源文件）。"""
    seen: set[str] = set()
    result: list[str] = []
    for m in _DOC_URL_RE.finditer(text):
        url = m.group(0).rstrip(".,;:)]}")
        if _ASSET_EXT_RE.search(url):
            continue
        if url in seen:
            continue
        seen.add(url)
        result.append(url)
    return result


def _probe_api_urls(site, http: httpx.Client, cfg: dict, settings) -> list[str]:
    """逐个探活候选 JSON API 端点，从 JSON 中递归提取文档 URL。"""
    candidates = [str(x) for x in (cfg.get("api_candidates") or [])]
    for api_url in candidates:
        wait_before_request(site.code, site.rate_limit)
        try:
            resp = http.get(api_url, timeout=settings.crawl_timeout_seconds)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            log.debug("API 端点探活失败 %s: %s", api_url, exc)
            continue
        urls = _extract_urls_from_json(data, str(resp.url))
        if urls:
            log.info("API 端点探活成功 %s：%d 个文档链接", api_url, len(urls))
            return urls
    return []


def _extract_urls_from_json(data, base_url: str) -> list[str]:
    """递归遍历 JSON，收集 documentation.espressif.com 的文档 URL。"""
    found: list[str] = []
    seen: set[str] = set()

    def walk(node) -> None:
        if isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)
        elif isinstance(node, str):
            if "documentation.espressif.com" in node:
                for m in _DOC_URL_RE.finditer(node):
                    url = m.group(0).rstrip(".,;:)]}")
                    if _ASSET_EXT_RE.search(url) or url in seen:
                        continue
                    seen.add(url)
                    found.append(url)

    walk(data)
    return found
