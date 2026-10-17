"""时间工具：爬虫侧统一 naive UTC。

约定：SQLite 无时区类型，所有时间字段一律存 naive UTC
（datetime.utcnow() 在 Python 3.12 已弃用，统一从这里取）。
"""
from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
