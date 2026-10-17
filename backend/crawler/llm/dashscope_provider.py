"""阿里云百炼 DashScope Provider（OpenAI 兼容模式）。

2026-09 现状要点：
- chat 走 /compatible-mode/v1 路径；
- qwen3.x 新系列默认开启思考模式，思考 token 额外计费——统一显式
  enable_thinking: false（见 config/models.yaml 的 disable_thinking）；
- API Key 与知识库主应用共享同一份 backend/.env（DASHSCOPE_API_KEY）。
"""
from __future__ import annotations

import logging
import time

from openai import BadRequestError, OpenAI

from ..settings import get_settings
from .base import ChatResult

log = logging.getLogger(__name__)


class DashScopeChatProvider:
    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        settings = get_settings()
        api_key = api_key or settings.dashscope_api_key
        if not api_key:
            raise RuntimeError(
                "未配置 DASHSCOPE_API_KEY：请复制 .env.example 为 .env 并填入阿里云百炼 API Key"
            )
        self._client = OpenAI(
            api_key=api_key,
            base_url=base_url or settings.llm_base_url,
            timeout=120,
            max_retries=2,
        )

    @property
    def client(self) -> OpenAI:
        return self._client

    def chat(
        self,
        messages: list[dict],
        model: str,
        *,
        json_mode: bool = False,
        disable_thinking: bool = True,
        max_tokens: int = 2000,
        temperature: float = 0.2,
    ) -> ChatResult:
        start = time.monotonic()
        kwargs: dict = dict(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        try:
            if disable_thinking:
                kwargs["extra_body"] = {"enable_thinking": False}
            resp = self._client.chat.completions.create(**kwargs)
        except BadRequestError as exc:
            # 个别模型不接受 enable_thinking 参数 → 去掉后重试一次
            if "enable_thinking" not in str(exc):
                raise
            kwargs.pop("extra_body", None)
            resp = self._client.chat.completions.create(**kwargs)

        usage = resp.usage
        return ChatResult(
            content=(resp.choices[0].message.content or "").strip(),
            tokens_in=usage.prompt_tokens if usage else 0,
            tokens_out=usage.completion_tokens if usage else 0,
            latency_ms=int((time.monotonic() - start) * 1000),
            model=model,
        )
