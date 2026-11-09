# ============================================================
# 接口限流 —— 进程内令牌桶
#
# 适用范围：问答类高成本接口（/chat/ask、/chat/stream、/openapi/v1/ask）
# 说明：单进程部署下的轻量实现；多进程/多实例部署时每个进程独立计数，
#      如需全局限额请替换为 Redis 令牌桶。
# ============================================================

import threading
import time
from dataclasses import dataclass
from typing import Dict

from fastapi import Depends, Request

from app.api.deps import get_current_active_user, get_api_client
from app.core.config import settings
from app.core.exceptions import RateLimitedException
from app.models.api_client import ApiClient
from app.models.user import User


@dataclass
class _Bucket:
    """令牌桶状态：tokens=当前可用令牌数，updated_at=上次补充时间"""

    tokens: float
    updated_at: float


_buckets: Dict[str, _Bucket] = {}
_lock = threading.Lock()
_last_cleanup = time.monotonic()
_CLEANUP_INTERVAL = 300      # 每 5 分钟清理一次长期未使用的桶


def _consume(key: str) -> None:
    """按令牌桶算法消费一个令牌；不足则抛 429"""
    now = time.monotonic()
    rate = settings.RATE_LIMIT_PER_MINUTE / 60.0
    capacity = float(settings.RATE_LIMIT_BURST)

    with _lock:
        bucket = _buckets.get(key)
        if bucket is None:
            bucket = _Bucket(tokens=capacity, updated_at=now)
            _buckets[key] = bucket

        # 按经过时间补充令牌（上限为桶容量）
        elapsed = now - bucket.updated_at
        bucket.tokens = min(capacity, bucket.tokens + elapsed * rate)
        bucket.updated_at = now

        if bucket.tokens < 1.0:
            retry_after = max(1, int((1.0 - bucket.tokens) / rate) + 1)
            raise RateLimitedException(retry_after=retry_after)

        bucket.tokens -= 1.0
        _cleanup_stale(now)


def _cleanup_stale(now: float) -> None:
    """清理超过 1 小时未使用的桶，避免内存无限增长（调用方需持有锁）"""
    global _last_cleanup
    if now - _last_cleanup < _CLEANUP_INTERVAL:
        return
    _last_cleanup = now
    stale = [k for k, b in _buckets.items() if now - b.updated_at > 3600]
    for k in stale:
        _buckets.pop(k, None)


def rate_limit_chat(
    request: Request,
    current_user: User = Depends(get_current_active_user),
) -> User:
    """问答接口限流依赖（按登录用户维度计数）"""
    if settings.RATE_LIMIT_ENABLED:
        _consume(f"user:{current_user.id}")
    return current_user


def rate_limit_open_api(
    request: Request,
    client: ApiClient = Depends(get_api_client),
) -> ApiClient:
    """开放 API 限流依赖（按 API Key 凭证维度计数）"""
    if settings.RATE_LIMIT_ENABLED:
        _consume(f"apikey:{client.id}")
    return client


def rate_limit_tts(
    request: Request,
    current_user: User = Depends(get_current_active_user),
) -> User:
    """语音合成限流依赖（独立计数，避免与问答额度互相挤占）"""
    if settings.RATE_LIMIT_ENABLED:
        _consume(f"tts:user:{current_user.id}")
    return current_user
