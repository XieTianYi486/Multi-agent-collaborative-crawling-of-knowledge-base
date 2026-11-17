"""robots.txt 许可检查。

发现式采集会抓到未备案域名，必须遵守对方 robots.txt：
- 按 scheme://host 缓存解析结果，一次流水线内不重复拉取；
- robots.txt 不存在（4xx）或拉取失败时放行，但记录日志便于事后审计。
"""
from __future__ import annotations

import logging
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx

log = logging.getLogger(__name__)

_cache: dict[str, RobotFileParser | None] = {}


def is_allowed(http: httpx.Client, url: str) -> bool:
    """判断 URL 是否允许抓取（无法判断时放行）。"""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return False
    origin = f"{parts.scheme}://{parts.netloc}"
    if origin not in _cache:
        _cache[origin] = _load(http, origin + "/robots.txt")
    rp = _cache[origin]
    if rp is None:
        return True
    try:
        return rp.can_fetch("*", url)
    except Exception:  # noqa: BLE001 - 解析异常按放行处理
        return True


def _load(http: httpx.Client, robots_url: str) -> RobotFileParser | None:
    try:
        resp = http.get(robots_url, timeout=10)
        if resp.status_code >= 400:
            return None
        rp = RobotFileParser()
        rp.parse(resp.text.splitlines())
        return rp
    except Exception as exc:  # noqa: BLE001 - 网络异常放行
        log.info("robots.txt 获取失败（放行）%s: %s", robots_url, exc)
        return None
