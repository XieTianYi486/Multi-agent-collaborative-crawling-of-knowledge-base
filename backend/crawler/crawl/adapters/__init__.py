"""适配器注册表：adapter 名 → fetch 函数。

新增数据源三步：
1. 在 config/sites.yaml 加站点条目并指定 adapter；
2. 若为已支持的采集方式（rss/html_list/sitemap/github），直接复用现成适配器；
3. 新采集方式才在本目录新增模块并注册。
"""
from __future__ import annotations

from .base import RawItem
from .espressif_docs import fetch as fetch_espressif_docs
from .github import fetch as fetch_github
from .html_list import fetch as fetch_html_list
from .rss_feed import fetch as fetch_rss
from .sitemap import fetch as fetch_sitemap

_REGISTRY = {
    "rss_feed": fetch_rss,
    "html_list": fetch_html_list,
    "sitemap": fetch_sitemap,
    "github": fetch_github,
    "espressif_docs": fetch_espressif_docs,
}


def get_adapter(name: str):
    return _REGISTRY.get(name)


def register_adapter(name: str, fn) -> None:
    """注册自定义适配器（测试注入用）。"""
    _REGISTRY[name] = fn


__all__ = ["RawItem", "get_adapter", "register_adapter"]
