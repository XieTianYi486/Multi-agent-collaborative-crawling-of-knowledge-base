"""摘要 Agent（Summarizer）：一句话中文摘要，仅存爬虫库（KB 无 summary 列）。

LLM 不可用/超预算时跳过，不影响后续步骤。
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

_PROMPT_FILE = CONFIG_DIR / "prompts" / "summarizer.md"


def _system_prompt() -> str:
    return _PROMPT_FILE.read_text(encoding="utf-8")


def _user_content(doc: Document) -> str:
    return f"请摘要以下技术文章：\n标题：{doc.title[:200]}\n正文节选：{(doc.text or '')[:500]}"


def summarize_documents(session: Session, docs: list[Document]) -> int:
    """给文档生成一句话摘要，返回成功数。"""
    spec = registry.get_spec("summarizer")
    provider = registry.get_chat_provider()
    if spec is None or provider is None:
        return 0
    usage.ensure_budget(session, "summarizer")

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

    results, batch_used, tokens_in, tokens_out = call_many(provider, spec.model, requests, max_tokens=200)

    summarized = 0
    for doc in docs:
        content = results.get(str(doc.id))
        if not content:
            continue
        data = parse_json_response(content)
        if not data:
            log.warning("摘要结果不是合法 JSON（doc %d），跳过", doc.id)
            continue
        doc.summary = str(data.get("summary", ""))[:200]
        doc.is_summarized = True
        summarized += 1

    usage.record_call(
        session, task="summarizer", spec=spec, batch=batch_used,
        tokens_in=max(tokens_in, 1), tokens_out=max(tokens_out, 1), latency_ms=0,
    )
    log.info("摘要完成：%d/%d 篇（%s）", summarized, len(docs), "批量" if batch_used else "顺序")
    return summarized
