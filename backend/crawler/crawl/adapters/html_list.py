"""通用 HTML 列表适配器：配置驱动的「列表页 → 详情页」采集。

适用于静态 HTML 站点（论坛 / 新闻列表 / 文档目录），无需 JS 渲染。

sites.yaml config 配置项：
- list_url:      列表页 URL（必填）
- link_selector: 条目链接的 CSS 选择器（必填，如 "a.s.xst" / "a.reference.internal"）
- mode:          "list"（默认）—— 列表页直接出条目；
                 "tree" —— 列表页链接先抓取，再从每页提取同选择器的子链接
                 （用于文档目录的两层级联采集）
- max_items:     单次最多返回条数（默认 40，超出部分下轮增量补齐）
- exclude:       链接 URL 需排除的子串列表
- user_agent:    站点级 UA 覆盖（个别官方站 WAF 拦截爬虫 UA 时使用，
                 仅限官方公开内容站点，论坛/社区不适用）

礼貌性：详情页抓取前按站点 rate_limit 限速；crawl 层注入已知 URL，
已入库的详情页不重复抓取（增量）。
"""
from __future__ import annotations

import logging
import re
from urllib.parse import urljoin

import httpx
from lxml import html as lxml_html

from ...settings import get_settings
from ..politeness import wait_before_request
from .base import RawItem
from .known import is_known, page_title

log = logging.getLogger(__name__)


def _extract_links(doc, selector: str, base_url: str, excludes: list[str]) -> list[tuple[str, str]]:
    """从文档中提取 (绝对URL, 链接文本) 列表（按出现顺序去重）。"""
    doc.make_links_absolute(base_url)
    seen: set[str] = set()
    result: list[tuple[str, str]] = []
    for a in doc.cssselect(selector):
        href = (a.get("href") or "").strip()
        if not href or href.startswith(("javascript:", "mailto:", "#")):
            continue
        href = href.split("#")[0]
        if any(ex in href for ex in excludes):
            continue
        if href in seen:
            continue
        seen.add(href)
        text = re.sub(r"\s+", " ", "".join(a.itertext())).strip()
        result.append((href, text))
    return result


def fetch(site, http: httpx.Client) -> list[RawItem]:
    # 兼容 ORM Site（config_json）与 SiteConfig（config）两种来源
    cfg = getattr(site, "config_json", None) or getattr(site, "config", None) or {}
    list_url = cfg.get("list_url") or ""
    selector = cfg.get("link_selector") or "a"
    mode = cfg.get("mode", "list")
    max_items = int(cfg.get("max_items", 40))
    excludes = [str(x) for x in (cfg.get("exclude") or [])]
    # 站点级 UA 覆盖（仅官方公开内容站点的 WAF 兼容场景）
    site_ua = cfg.get("user_agent") or ""

    if not list_url:
        log.warning("站点 %s 未配置 list_url，跳过", site.code)
        return []

    settings = get_settings()

    def get(url: str) -> httpx.Response:
        kwargs = {"timeout": settings.crawl_timeout_seconds}
        if site_ua:
            kwargs["headers"] = {"User-Agent": site_ua}
        return http.get(url, **kwargs)

    # 1. 列表页 → 候选链接（用 resp.text：httpx 自带 charset 检测，
    #    兼容无 charset 声明的 GBK 中文站点）
    wait_before_request(site.code, site.rate_limit)
    resp = get(list_url)
    resp.raise_for_status()
    list_doc = lxml_html.fromstring(resp.text)
    candidates = _extract_links(list_doc, selector, str(resp.url), excludes)

    # 2. tree 模式：抓取每个候选页，再提取同选择器的子链接（文档目录层级）
    detail_urls: list[tuple[str, str]] = list(candidates)
    if mode == "tree":
        sub_urls: list[tuple[str, str]] = []
        for url, _title in candidates:
            wait_before_request(site.code, site.rate_limit)
            try:
                page = get(url)
                page.raise_for_status()
                sub_doc = lxml_html.fromstring(page.text)
                sub_urls.extend(_extract_links(sub_doc, selector, str(page.url), excludes))
            except Exception as exc:  # noqa: BLE001 - 单页失败不影响整体
                log.warning("文档目录页抓取失败 %s: %s", url, exc)
        # 子链接优先（叶子内容页），目录页排在后面
        detail_urls = sub_urls + detail_urls

    # 3. 逐个抓详情页（已入库的跳过，增量采集）
    items: list[RawItem] = []
    for url, title in detail_urls:
        if len(items) >= max_items:
            break
        if is_known(url):
            continue
        wait_before_request(site.code, site.rate_limit)
        try:
            resp = get(url)
            resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001 - 单页失败不影响整体
            log.warning("详情页抓取失败 %s: %s", url, exc)
            continue
        page_title_text = page_title(resp.text) or title
        items.append(RawItem(
            url=str(resp.url),
            title=page_title_text[:500],
            content_html=resp.text,
        ))
    log.info("站点 %s：候选 %d，本轮抓取 %d 篇", site.code, len(detail_urls), len(items))
    return items
