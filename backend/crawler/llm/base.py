"""LLM Provider 抽象接口。

当前实现：DashScope（阿里云百炼，OpenAI 兼容模式）。
未来接入上海合作方模型：实现同一接口（partner_provider.py），业务代码零改动。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Protocol


@dataclass
class ChatResult:
    """一次对话调用的完整结果（内容 + 用量，供成本账本记账）。"""

    content: str
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    model: str = ""


class ChatProvider(Protocol):
    def chat(
        self,
        messages: list[dict],
        model: str,
        *,
        json_mode: bool = False,
        disable_thinking: bool = True,
        max_tokens: int = 2000,
        temperature: float = 0.2,
    ) -> ChatResult: ...


_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.S)


def parse_json_response(content: str) -> dict | None:
    """解析模型返回的 JSON（容忍 ```json 围栏与前后杂文本），失败返回 None。"""
    text = content.strip()
    m = _FENCE_RE.search(text)
    if m:
        text = m.group(1).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # 尝试截取第一个 { 到最后一个 }
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            return None
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return data if isinstance(data, dict) else None
