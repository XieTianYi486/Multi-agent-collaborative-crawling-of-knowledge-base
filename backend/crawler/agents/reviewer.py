"""内容审核 Agent（Reviewer）：拦截广告/垃圾/版权高风险内容。

LLM 不可用/超预算时跳过——入库同步器用规则默认值兜底：
low 风险源默认通过、medium 风险源（已是节选）默认通过。
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from ..llm import registry, usage
from ..llm.base import parse_json_response
from ..llm.call import call_many
from ..settings import CONFIG_DIR
from ..store.models import Document

log = logging.getLogger(__name__)

_PROMPT_FILE = CONFIG_DIR / "prompts" / "reviewer.md"


def _system_prompt() -> str:
    return _PROMPT_FILE.read_text(encoding="utf-8")


def _user_content(doc: Document) -> str:
    return f"请审核以下采集条目：\n标题：{doc.title[:200]}\n正文节选：{(doc.text or '')[:500]}"


def review_documents(session: Session, docs: list[Document]) -> int:
    """审核文档（review_pass/review_reason），返回审核数。

    LLM 不可用/超预算返回 0（同步器按站点风险级规则兜底）。
    """
    spec = registry.get_spec("reviewer")
    provider = registry.get_chat_provider()
    if spec is None or provider is None:
        return 0
    usage.ensure_budget(session, "reviewer")

    system = _system_prompt()
    requests = [
        {
            "custom_id": str(doc.id),
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": _user_content(doc)},
            ],
        }
        for doc in docs
    ]

    results, batch_used, tokens_in, tokens_out = call_many(provider, spec.model, requests, max_tokens=400)

    reviewed = 0
    for doc in docs:
        content = results.get(str(doc.id))
        if not content:
            continue
        data = parse_json_response(content)
        if not data:
            log.warning("审核结果不是合法 JSON（doc %d），跳过", doc.id)
            continue
        doc.review_pass = bool(data.get("pass", True))
        doc.review_reason = str(data.get("reason", ""))[:500]
        doc.is_reviewed = True
        reviewed += 1

    usage.record_call(
        session, task="reviewer", spec=spec, batch=batch_used,
        tokens_in=max(tokens_in, 1), tokens_out=max(tokens_out, 1), latency_ms=0,
    )
    log.info("审核完成：%d/%d 篇（%s）", reviewed, len(docs), "批量" if batch_used else "顺序")
    return reviewed
