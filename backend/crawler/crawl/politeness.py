"""采集礼貌性：站点级限速 + 连续失败熔断。

原则（写入站点档案）：
- 每站点独立限速，尊重 429/Retry-After；
- 连续失败 3 次 → 熔断 6 小时，避免持续骚扰对方服务器。
"""
from __future__ import annotations

import logging
import time
from datetime import timedelta

from ..timeutil import utcnow

log = logging.getLogger(__name__)

# 站点 code → 上次请求时间（进程内）
_last_request: dict[str, float] = {}

BREAKER_FAILURES = 3
BREAKER_HOURS = 6


def wait_before_request(site_code: str, min_interval: float) -> None:
    """请求前等待，保证同一站点两次请求间隔 >= min_interval 秒。"""
    last = _last_request.get(site_code, 0.0)
    wait = min_interval - (time.monotonic() - last)
    if wait > 0:
        time.sleep(wait)
    _last_request[site_code] = time.monotonic()


def is_circuit_open(site) -> bool:
    """站点是否处于熔断期。"""
    return bool(site.breaker_until and utcnow() < site.breaker_until)


def record_site_success(site) -> None:
    site.consecutive_failures = 0
    site.last_crawled_at = utcnow()


def record_site_failure(site) -> None:
    site.consecutive_failures += 1
    if site.consecutive_failures >= BREAKER_FAILURES:
        site.breaker_until = utcnow() + timedelta(hours=BREAKER_HOURS)
        site.consecutive_failures = 0  # 熔断后重置计数，解禁后重新累计
        log.warning("站点 %s 连续失败，熔断 %d 小时", site.code, BREAKER_HOURS)
