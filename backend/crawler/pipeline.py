"""每日流水线（run_daily）：多智能体协作采集 → 自动入库知识库。

步骤全部幂等：同一批数据重复执行不产生重复文档/重复索引。
LLM 步骤均为 optional：API 不可用或超预算时自动跳过，规则管线照常运行。

流水线拓扑：
  crawl（必需）→ tagger（LLM,可选）→ review（LLM,可选）→ summarize（LLM,可选）
              └→ kb_sync（必需，读前序智能体产物，单文档容错）
"""
from __future__ import annotations

import logging

from .agents import reviewer, summarizer, tagger
from .agents.orchestrator import Orchestrator, Step
from .crawl.crawl import run_crawl
from .settings import get_settings
from .store import repo
from .store.db import init_db, session_scope

log = logging.getLogger(__name__)


def run_daily(ctx: dict | None = None, on_step: object = None) -> dict:
    """一键跑完整每日流水线。

    ctx 可传 {"site_codes": [...]}（调试只采指定站点）；
    on_step(step_name, StepResult) 每步完成时回调（UI 实时状态用）。
    """
    ctx = {} if ctx is None else ctx
    init_db()
    with session_scope() as session:
        repo.sync_sites(session)

    steps = [
        Step("crawl", _step_crawl),
        Step("tagger", _step_tagger, deps=("crawl",), optional=True),
        Step("review", _step_review, deps=("crawl",), optional=True),
        Step("summarize", _step_summarize, deps=("crawl",), optional=True),
        # kb_sync 依赖全部智能体步骤：skipped（预算/LLM不可用）也视为已完成，
        # 此时入库同步器用规则默认值兜底
        Step("kb_sync", _step_kb_sync, deps=("tagger", "review", "summarize")),
    ]
    return Orchestrator(steps).run(ctx, on_step_done=on_step)


# ---------------------------------------------------------------- 步骤实现


def _step_crawl(ctx: dict) -> None:
    stats = run_crawl(ctx.get("site_codes"))
    ctx["crawl_stats"] = stats
    log.info("采集完成：新增 %d，去重 %d，失败条目 %d",
             stats.new_docs, stats.dup_docs, stats.failed_items)
    for r in stats.site_results:
        log.info("  站点 %s: %s（新增 %d，去重 %d）",
                 r["code"], r["status"], r.get("new", 0), r.get("dup", 0))


def _step_tagger(ctx: dict) -> None:
    from .sync.ingest import ensure_crawl_categories, _kb_session

    with session_scope() as session:
        docs = repo.untagged_documents(session)
        if not docs:
            return
        # 分类候选列表运行时从知识库 categories 表查出（约束模型只能选真实分类名）
        kb_db = _kb_session()
        try:
            category_map = ensure_crawl_categories(kb_db)
        finally:
            kb_db.close()
        tagger.tag_documents(session, docs, list(category_map.keys()))


def _step_review(ctx: dict) -> None:
    with session_scope() as session:
        docs = repo.unreviewed_documents(session)
        if not docs:
            return
        reviewer.review_documents(session, docs)


def _step_summarize(ctx: dict) -> None:
    with session_scope() as session:
        docs = repo.unsummarized_documents(session)
        if not docs:
            return
        summarizer.summarize_documents(session, docs)


def _step_kb_sync(ctx: dict) -> None:
    from .sync.ingest import sync_documents

    settings = get_settings()
    stats = sync_documents(limit=settings.kb_sync_limit)
    ctx["kb_sync"] = stats
    log.info("知识库同步完成：成功 %d，跳过 %d，失败 %d",
             stats.synced, stats.skipped, stats.failed)
