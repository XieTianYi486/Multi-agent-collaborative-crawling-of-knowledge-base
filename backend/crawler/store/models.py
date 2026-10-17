"""SQLAlchemy 数据模型 —— 爬虫侧独立库（backend/crawler/data/crawler.db）。

设计原则：
- 与知识库主库分库：采集状态可整体删除重建，不影响主库；
- 唯一索引承担去重/幂等职责，保证每日流水线可重复执行；
- 版权合规（source_authorizations）与成本（llm_usage）都留痕可审计。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from typing import Optional

from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from ..timeutil import utcnow


class Base(DeclarativeBase):
    pass


class Site(Base):
    """站点档案（config/sites.yaml 的入库镜像）。"""

    __tablename__ = "sites"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    source_type: Mapped[str] = mapped_column(String(16), default="rss")  # rss/api/html
    adapter: Mapped[str] = mapped_column(String(64), default="")
    base_url: Mapped[str] = mapped_column(String(512), default="")
    risk_level: Mapped[str] = mapped_column(String(8), default="low")  # low/medium/high
    authority_weight: Mapped[float] = mapped_column(Float, default=1.0)
    rate_limit: Mapped[float] = mapped_column(Float, default=5.0)  # 请求最小间隔（秒）
    license_note: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    config_json: Mapped[dict] = mapped_column(JSON, default=dict)

    # --- 采集健康度 ---
    last_crawled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    breaker_until: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)  # 熔断截止时间


class CrawlTask(Base):
    """每次采集任务的审计记录（失败率监控、断点排查）。"""

    __tablename__ = "crawl_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="running")  # running/ok/failed
    new_docs: Mapped[int] = mapped_column(Integer, default=0)
    dup_docs: Mapped[int] = mapped_column(Integer, default=0)
    failed_items: Mapped[int] = mapped_column(Integer, default=0)
    error_log: Mapped[str] = mapped_column(Text, default="")


class Document(Base):
    """采集到的文档主数据。"""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id"), index=True)
    url: Mapped[str] = mapped_column(String(1024), default="")
    url_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    # 内容哈希：跨源转载检测（同一内容不同 URL）；中高风险源用节选计算
    content_hash: Mapped[Optional[str]] = mapped_column(String(64), unique=True, nullable=True)
    simhash: Mapped[Optional[str]] = mapped_column(String(16), nullable=True, index=True)  # 64位 SimHash(hex)
    title: Mapped[str] = mapped_column(String(512), default="")
    author: Mapped[str] = mapped_column(String(256), default="")
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    lang: Mapped[str] = mapped_column(String(8), default="zh")

    summary: Mapped[str] = mapped_column(Text, default="")  # LLM 摘要（仅存爬虫库）
    category: Mapped[str] = mapped_column(String(64), default="")  # LLM 打标 → KB 分类名
    keywords: Mapped[list] = mapped_column(JSON, default=list)
    relevant: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)  # 教学相关（LLM 判定）

    content_md_path: Mapped[str] = mapped_column(String(512), default="")  # 相对 data/ 的 Markdown 路径
    text: Mapped[str] = mapped_column(Text, default="")  # 纯文本（去重/打标用）

    license_status: Mapped[str] = mapped_column(String(16), default="low")
    meta_json: Mapped[dict] = mapped_column(JSON, default=dict)

    # --- 智能体流水线状态位 ---
    is_tagged: Mapped[bool] = mapped_column(Boolean, default=False)
    is_reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    review_pass: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)  # LLM 审核结论
    review_reason: Mapped[str] = mapped_column(Text, default="")
    is_summarized: Mapped[bool] = mapped_column(Boolean, default=False)

    site: Mapped["Site"] = relationship()


class KnowledgeBaseSync(Base):
    """采集文档 → 知识库主库 的同步留痕（幂等：每篇文档只推一次）。"""

    __tablename__ = "kb_syncs"

    id: Mapped[int] = mapped_column(primary_key=True)
    doc_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), unique=True, index=True)
    kb_doc_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 知识库侧文档ID
    title: Mapped[str] = mapped_column(String(512), default="")
    status: Mapped[str] = mapped_column(String(16), default="ok")  # ok/failed/skipped
    error: Mapped[str] = mapped_column(Text, default="")
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class SourceAuthorization(Base):
    """版权合规留痕：每个站点的授权依据（仅校内教学使用声明）。"""

    __tablename__ = "source_authorizations"

    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id"), index=True)
    auth_type: Mapped[str] = mapped_column(String(32), default="")  # 官方API/RSS公开/站点档案声明
    scope: Mapped[str] = mapped_column(String(128), default="校内教学，不对外分发")
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    reviewer: Mapped[str] = mapped_column(String(64), default="")
    note: Mapped[str] = mapped_column(Text, default="")


class LlmUsage(Base):
    """LLM 成本账本 —— 预算闸门与成本审计的数据源。"""

    __tablename__ = "llm_usage"

    id: Mapped[int] = mapped_column(primary_key=True)
    task: Mapped[str] = mapped_column(String(64), index=True)
    provider: Mapped[str] = mapped_column(String(32), default="dashscope")
    model: Mapped[str] = mapped_column(String(64), default="")
    batch: Mapped[bool] = mapped_column(Boolean, default=False)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    cost_est: Mapped[float] = mapped_column(Float, default=0.0)  # 元（按 models.yaml 价格估算）
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="ok")  # ok/failed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
