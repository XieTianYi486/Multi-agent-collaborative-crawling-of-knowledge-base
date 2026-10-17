"""批量/顺序调用的统一封装：批量接口优先（半价），失败自动回退顺序调用。

返回真实 token 用量，供成本账本记账。
"""
from __future__ import annotations

import logging

from ..settings import get_settings
from . import registry

log = logging.getLogger(__name__)


def call_many(
    provider,
    model: str,
    requests: list[dict],
    *,
    max_tokens: int = 800,
) -> tuple[dict[str, str], bool, int, int]:
    """批量执行对话请求（json_mode）。

    requests: [{"custom_id": str, "messages": [...]}]
    返回 ({custom_id: content}, 是否批量, 输入token, 输出token)。
    """
    settings = get_settings()
    # 请求过少时批量接口的排队延迟远大于省钱收益，直接走顺序调用
    if settings.llm_batch_enabled and len(requests) >= 5:
        batch_client = registry.get_batch_client()
        if batch_client is not None:
            try:
                batch_results = batch_client.submit(
                    requests, model, json_mode=True, max_tokens=max_tokens
                )
            except Exception as exc:  # noqa: BLE001 - 批量异常必须兜底
                log.warning("批量调用异常，回退顺序调用: %s", exc)
                batch_results = None
            if batch_results is not None:
                contents = {cid: r[0] for cid, r in batch_results.items()}
                tokens_in = sum(r[1] for r in batch_results.values())
                tokens_out = sum(r[2] for r in batch_results.values())
                return contents, True, tokens_in, tokens_out

    contents: dict[str, str] = {}
    tokens_in = tokens_out = 0
    for req in requests:
        try:
            resp = provider.chat(
                req["messages"], model, json_mode=True, disable_thinking=True, max_tokens=max_tokens
            )
            contents[req["custom_id"]] = resp.content
            tokens_in += resp.tokens_in
            tokens_out += resp.tokens_out
        except Exception as exc:  # noqa: BLE001 - 单条失败不影响其余
            log.warning("顺序调用失败（%s）: %s", req["custom_id"], exc)
    return contents, False, tokens_in, tokens_out
