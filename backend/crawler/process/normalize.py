"""文本归一化：统一换行、折叠空白、清理控制字符与 HTML 残留。"""
from __future__ import annotations

import re

_WS_RE = re.compile(r"[ \t　]+")
_NL_RE = re.compile(r"\n{3,}")
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
# HTML 残留（正文抽取失败时 RSS 摘要里可能残留标签与实体）
_TAG_RE = re.compile(r"<[^>]{1,300}>")
_ENTITY_RE = re.compile(r"&[a-z#0-9]{1,12};")


def normalize_text(text: str) -> str:
    """纯文本归一化：去 HTML 标签/实体、控制字符，统一换行、折叠空白。"""
    text = _TAG_RE.sub(" ", text or "")
    text = _ENTITY_RE.sub(" ", text)
    text = _CTRL_RE.sub("", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _WS_RE.sub(" ", text)
    text = _NL_RE.sub("\n\n", text)
    return text.strip()
