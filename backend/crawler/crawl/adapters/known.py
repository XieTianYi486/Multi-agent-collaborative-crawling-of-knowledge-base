"""已知 URL 共享池：crawl 层在每次采集前注入已入库详情页 URL，
列表/树形/站点地图适配器据此跳过，实现增量采集。"""
from __future__ import annotations

import re

from lxml import html as lxml_html

# 已知（已入库）详情页 URL
_known_urls: set[str] = set()


def set_known_urls(urls: set[str]) -> None:
    global _known_urls
    _known_urls = {u.strip() for u in urls if u}


def is_known(url: str) -> bool:
    return url in _known_urls


def page_title(content: str) -> str:
    """从 HTML <title> 提取页面标题。"""
    try:
        doc = lxml_html.fromstring(content)
        title_el = doc.cssselect("title")
        if title_el and title_el[0].text:
            return re.sub(r"\s+", " ", title_el[0].text).strip()
    except Exception:  # noqa: BLE001
        pass
    return ""
