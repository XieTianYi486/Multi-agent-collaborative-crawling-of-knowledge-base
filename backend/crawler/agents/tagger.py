"""分类打标 Agent（Tagger）：分类映射到知识库 Category 树 + 相关度 + 关键词。

成本策略：qwen-flash 批量接口（半价），输入仅标题 + 正文前 500 字；
LLM 不可用/超预算时跳过（relevance 留空，入库同步器用规则默认值兜底）。
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

_PROMPT_FILE = CONFIG_DIR / "prompts" / "tagger.md"


def _system_prompt(categories: list[str]) -> str:
    template = _PROMPT_FILE.read_text(encoding="utf-8")
    # 分类候选列表运行时从知识库 categories 表注入（约束模型只能选真实分类名）
    return template.replace("{{categories}}", "\n".join(f"- {c}" for c in categories))


def _user_content(doc: Document) -> str:
    return f"请对以下内容分类打标：\n标题：{doc.title[:200]}\n正文节选：{(doc.text or '')[:500]}"


def tag_documents(session: Session, docs: list[Document], categories: list[str]) -> int:
    """给文档打标（category/keywords/relevant），返回成功数。

    优先批量接口，失败自动回退顺序调用；LLM 不可用/超预算返回 0。
    """
    spec = registry.get_spec("tagger")
    provider = registry.get_chat_provider()
    if spec is None or provider is None or not categories:
        return 0
    usage.ensure_budget(session, "tagger")

    system = _system_prompt(categories)
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

    results, batch_used, tokens_in, tokens_out = call_many(provider, spec.model, requests, max_tokens=800)

    tagged = 0
    for doc in docs:
        content = results.get(str(doc.id))
        if not content:
            continue
        data = parse_json_response(content)
        if not data:
            log.warning("打标结果不是合法 JSON（doc %d），跳过", doc.id)
            continue
        doc.category = str(data.get("category", ""))[:60]
        doc.relevant = bool(data.get("relevant", False))
        doc.keywords = [str(k)[:30] for k in data.get("keywords", [])][:10]
        doc.is_tagged = True
        tagged += 1

    usage.record_call(
        session, task="tagger", spec=spec, batch=batch_used,
        tokens_in=max(tokens_in, 1), tokens_out=max(tokens_out, 1), latency_ms=0,
    )
    log.info("打标完成：%d/%d 篇（%s）", tagged, len(docs), "批量" if batch_used else "顺序")
    return tagged
