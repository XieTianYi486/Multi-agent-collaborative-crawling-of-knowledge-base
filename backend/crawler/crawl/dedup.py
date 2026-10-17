"""内容去重：URL 精确去重 + 内容哈希 + SimHash 近重复检测。

三层策略（采集入口按序执行）：
1. url_hash      —— 同一 URL 不重复抓；
2. content_hash  —— 相同内容不同 URL（镜像/移动端页面）；
3. simhash       —— 近重复（跨源转载，海明距离 <= 阈值判重）。
"""
from __future__ import annotations

import hashlib
import re
from collections import Counter
from urllib.parse import urlsplit, urlunsplit

import jieba

from ..settings import get_settings

_WS_RE = re.compile(r"\s+")
_EN_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9\-\.]{1,30}")


def normalize_url(url: str) -> str:
    """URL 规范化：去掉 fragment、尾部斜杠，统一小写 scheme/host。"""
    url = url.strip()
    parts = urlsplit(url)
    scheme = parts.scheme.lower() or "http"
    netloc = parts.netloc.lower()
    path = parts.path or "/"
    path = path.rstrip("/") or "/"
    return urlunsplit((scheme, netloc, path, parts.query, ""))


def url_hash(url: str) -> str:
    return hashlib.sha256(normalize_url(url).encode("utf-8")).hexdigest()


def normalize_text(text: str) -> str:
    """空白归一化（哈希与 SimHash 前调用）。"""
    return _WS_RE.sub(" ", text or "").strip()


def content_hash(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def _tokens(text: str) -> list[str]:
    """分词（jieba 中文 + 正则英文），返回小写词列表。"""
    text = normalize_text(text)
    tokens: list[str] = []
    for word in jieba.cut(text):
        word = word.strip().lower()
        if len(word) >= 2:
            tokens.append(word)
    tokens.extend(m.group() for m in _EN_TOKEN_RE.finditer(text.lower()))
    return tokens


def simhash64(text: str) -> str:
    """64 位 SimHash（返回 16 位 hex 字符串）。

    每个 token 以 MD5 展开为 64 个权重位，按词频累加后取符号位。
    """
    weights = [0] * 64
    for token, count in Counter(_tokens(text)).items():
        h = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
        for i in range(64):
            weights[i] += count if (h >> i) & 1 else -count
    value = 0
    for i, w in enumerate(weights):
        if w > 0:
            value |= 1 << i
    return format(value, "016x")


def hamming_distance(hex_a: str, hex_b: str) -> int:
    """两个 64 位 hex SimHash 的海明距离；任一为空视为完全不同。"""
    if not hex_a or not hex_b:
        return 64
    return bin(int(hex_a, 16) ^ int(hex_b, 16)).count("1")


def is_near_dup(hex_a: str, hex_b: str, threshold: int | None = None) -> bool:
    if threshold is None:
        threshold = get_settings().simhash_hamming_threshold
    return hamming_distance(hex_a, hex_b) <= threshold
