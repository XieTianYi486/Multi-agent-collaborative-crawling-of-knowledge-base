"""robots.txt 许可检查（RFC 9309 语义）。

发现式采集会抓到未备案域名，必须遵守对方 robots.txt：
- 按 scheme://host 缓存解析结果，带 TTL，失败/5xx 不会永久缓存；
- 4xx = 站点没有 robots.txt → 允许；
- 5xx / 网络错误 = 服务器状态不明 → **拒绝抓取**（RFC 9309 要求 fail-closed，
  不能因对方服务器抖动就跳过合规检查）；
- 用真实 User-Agent 匹配规则组（can_fetch("*") 会漏掉针对本 UA 的 Disallow 组）。

局限：urllib.robotparser 在 Python 3.9-3.12 不支持 RFC 9309 的
通配符（*）与最长匹配语义（3.13.14+ 才引入），遇到此类规则可能
解析偏差；本项目以"低风险源 + 仅存节选/链接 + 人工审核"兜底合规。
"""
from __future__ import annotations

import logging
import time
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from ..settings import get_settings

log = logging.getLogger(__name__)

# origin -> (RobotFileParser | None, 缓存时间戳)
_cache: dict[str, tuple[RobotFileParser | None, float]] = {}
# 解析成功缓存 1 小时；失败（5xx/网络错误）只缓存 5 分钟，避免长时间拒绝正常站点
_TTL_OK_SECONDS = 3600
_TTL_FAIL_SECONDS = 300


def is_allowed(http: httpx.Client, url: str) -> bool:
    """判断 URL 是否允许抓取（无法确认许可时按拒绝处理）。"""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return False
    origin = f"{parts.scheme}://{parts.netloc}"
    now = time.time()
    entry = _cache.get(origin)
    if entry is None or now - entry[1] > _ttl(entry[0]):
        rp = _load(http, origin + "/robots.txt")
        _cache[origin] = (rp, now)
        entry = (rp, now)
    rp = entry[0]
    if rp is None:
        return False
    try:
        user_agent = get_settings().crawl_user_agent or "*"
        return rp.can_fetch(user_agent, url)
    except Exception:  # noqa: BLE001 - 解析异常保守拒绝
        log.warning("robots.txt 规则解析异常，保守拒绝 %s", url)
        return False


def _ttl(rp: RobotFileParser | None) -> int:
    return _TTL_OK_SECONDS if rp is not None else _TTL_FAIL_SECONDS


def _load(http: httpx.Client, robots_url: str) -> RobotFileParser | None:
    try:
        resp = http.get(robots_url, timeout=10)
        if resp.status_code >= 500:
            log.info("robots.txt 返回 5xx（按拒绝处理，5 分钟后重试）%s", robots_url)
            return None
        if resp.status_code >= 400:
            # 4xx：站点没有 robots.txt → 空解析器（允许一切）
            return _empty_allowing_parser()
        rp = RobotFileParser()
        rp.parse(resp.text.splitlines())
        return rp
    except Exception as exc:  # noqa: BLE001 - 网络异常按拒绝处理
        log.info("robots.txt 获取失败（按拒绝处理，5 分钟后重试）%s: %s", robots_url, exc)
        return None


def _empty_allowing_parser() -> RobotFileParser:
    """构造"允许一切"的空解析器（等价于站点没有 robots.txt）。"""
    rp = RobotFileParser()
    rp.parse([])
    return rp
