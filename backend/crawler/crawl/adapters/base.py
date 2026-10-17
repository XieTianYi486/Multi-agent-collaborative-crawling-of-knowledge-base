"""适配器统一接口：每个数据源实现 fetch(site, http) -> list[RawItem]。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class RawItem:
    """采集到的原始条目（未去重、未解析）。"""

    url: str
    title: str = ""
    content_html: str | None = None  # 详情/摘要 HTML
    content_text: str | None = None  # 已有纯文本（API 源）
    published_at: datetime | None = None
    author: str = ""
    meta: dict = field(default_factory=dict)  # 自带信号：stars/releases 等
