# ============================================================
# 入库同步器测试：爬虫文档 → 知识库主库（测试库隔离）
# 覆盖：幂等闸门 / 自动过审 / 审核拦截 / 单文档失败不中断
# ============================================================

import pytest

from crawler.settings import SiteConfig
from crawler.store import db as cdb
from crawler.store import repo
from crawler.store.db import session_scope
from crawler.store.models import Document as CrawlDocument
from crawler.store.models import KnowledgeBaseSync, Site
from crawler.sync.ingest import CRAWL_CATEGORIES, sync_documents


@pytest.fixture()
def crawler_db():
    """初始化爬虫测试库（KB_DATA_DIR 已被 conftest 指向测试目录）。"""
    cdb.init_db()
    return cdb


@pytest.fixture()
def fake_process_task(monkeypatch):
    """替换真实的 _process_document_task（免 embedding 调用）。"""
    captured = {"ids": []}

    def fake(document_id):
        captured["ids"].append(document_id)
        # 模拟真实任务：置 status=1 并写一个 DocChunk
        from app.db.sqlite import SessionLocal
        from app.models.document import DocChunk, Document

        db = SessionLocal()
        doc = db.query(Document).filter(Document.id == document_id).first()
        if doc:
            doc.status = 1
            doc.chunk_count = 1
            db.add(DocChunk(document_id=document_id, chunk_index=0,
                            content=doc.title, chroma_id=f"doc_{document_id}_chunk_0"))
            db.commit()
        db.close()

    monkeypatch.setattr("app.tasks.document_tasks._process_document_task", fake)
    return captured


@pytest.fixture()
def upload_dir(tmp_path, monkeypatch):
    """把 UPLOAD_DIR 指向临时目录，避免污染真实 uploads/。"""
    from app.core.config import settings

    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    return tmp_path


def _add_crawler_doc(site_id: int, **kwargs):
    from crawler.crawl.dedup import content_hash, url_hash

    url = kwargs.pop("url", "https://example.com/doc/1")
    text = kwargs.pop("text", "ESP32 开发板入门教程")
    defaults = dict(
        site_id=site_id, url=url, url_hash=url_hash(url),
        content_hash=content_hash(text), simhash="0" * 16,
        title="ESP32 入门", text=text,
    )
    defaults.update(kwargs)
    return CrawlDocument(**defaults)


class TestCategories:
    def test_ensure_categories_idempotent(self, db):
        from crawler.sync.ingest import ensure_crawl_categories

        m1 = ensure_crawl_categories(db)
        m2 = ensure_crawl_categories(db)
        assert m1 == m2
        for name, _parent, _sort, _desc in CRAWL_CATEGORIES:
            assert name in m1


class TestSyncDocuments:
    def test_sync_and_idempotent(self, crawler_db, fake_process_task, upload_dir, db):
        # 1. 站点档案 + 一篇爬虫文档（内容唯一，规避同库其他用例的哈希碰撞）
        with session_scope() as s:
            repo.sync_sites(s, [SiteConfig(
                code="test_site_a", name="测试站点A", source_type="rss",
                adapter="rss_feed", risk_level="low",
                license_note="测试用", config={"feed_url": "https://x/feed"},
            )])
            site_id = s.query(Site).filter(Site.code == "test_site_a").first().id
            s.add(_add_crawler_doc(site_id=site_id, url="https://example.com/doc/a1",
                                   text="A1 独特测试内容：ESP32 蓝牙配网流程",
                                   category="ESP32", relevant=True,
                                   is_tagged=True, review_pass=True, is_reviewed=True))

        # 2. 第一轮同步
        stats = sync_documents(limit=10)
        assert stats.synced == 1
        assert fake_process_task["ids"]  # 真实调用被 monkeypatch 捕获

        # 3. KB 侧断言：已入库 + 自动过审 + 密级公开
        from app.models.document import Document as KbDocument

        kb_doc = db.query(KbDocument).filter(KbDocument.source_hash.isnot(None)).first()
        assert kb_doc is not None
        assert kb_doc.source_url == "https://example.com/doc/a1"
        assert kb_doc.status == 1
        assert kb_doc.review_status == 2
        assert kb_doc.security_level == 1
        assert kb_doc.category_id is not None
        assert "爬虫自动入库" in kb_doc.review_comment

        # 4. 幂等：第二轮不再处理（kb_syncs 唯一索引闸门 → 待同步列表为空）
        stats2 = sync_documents(limit=10)
        assert stats2.synced == 0
        assert stats2.skipped == 0

    def test_review_rejected_skipped(self, crawler_db, fake_process_task, upload_dir, db):
        with session_scope() as s:
            repo.sync_sites(s, [SiteConfig(
                code="test_site_b", name="测试站点B", source_type="rss",
                adapter="rss_feed", risk_level="low",
                license_note="测试用", config={"feed_url": "https://x/feed"},
            )])
            site_id = s.query(Site).filter(Site.code == "test_site_b").first().id
            s.add(_add_crawler_doc(
                site_id=site_id, url="https://example.com/ad",
                text="B2 独特内容：加微信 xxx 购买课程",
                review_pass=False, is_reviewed=True,
                review_reason="广告", category="", relevant=None,
            ))

        stats = sync_documents(limit=10)
        assert stats.synced == 0
        assert stats.skipped == 1
        # kb_syncs 留痕为 skipped（只查本篇文档的留痕，规避其他用例的行）
        with session_scope() as s:
            doc = s.query(CrawlDocument).filter(
                CrawlDocument.url == "https://example.com/ad").first()
            row = s.query(KnowledgeBaseSync).filter(
                KnowledgeBaseSync.doc_id == doc.id).first()
            assert row is not None
            assert row.status == "skipped"
            assert "广告" in row.error

    def test_single_doc_failure_does_not_interrupt(self, crawler_db, upload_dir, db, monkeypatch):
        # 注入一个在处理阶段必然失败的 fake task
        def failing_task(document_id):
            raise RuntimeError("embedding 服务不可用")

        monkeypatch.setattr("app.tasks.document_tasks._process_document_task", failing_task)

        with session_scope() as s:
            repo.sync_sites(s, [SiteConfig(
                code="test_site_c", name="测试站点C", source_type="rss",
                adapter="rss_feed", risk_level="low",
                license_note="测试用", config={"feed_url": "https://x/feed"},
            )])
            site_id = s.query(Site).filter(Site.code == "test_site_c").first().id
            s.add(_add_crawler_doc(site_id=site_id, url="https://example.com/bad",
                                   text="C3 独特内容一：失败的文档正文",
                                   category="ESP32", relevant=True, is_tagged=True))
            s.add(_add_crawler_doc(site_id=site_id, url="https://example.com/good",
                                   text="C4 独特内容二：另一篇文档正文",
                                   category="ESP32", relevant=True, is_tagged=True))

        stats = sync_documents(limit=10)
        # 两篇都失败（同一 fake task 必挂），但同步器本身不抛异常、留痕 failed
        assert stats.synced == 0
        assert stats.failed == 2
        with session_scope() as s:
            bad = s.query(CrawlDocument).filter(
                CrawlDocument.url == "https://example.com/bad").first()
            good = s.query(CrawlDocument).filter(
                CrawlDocument.url == "https://example.com/good").first()
            rows = s.query(KnowledgeBaseSync).filter(
                KnowledgeBaseSync.doc_id.in_([bad.id, good.id])).all()
            assert len(rows) == 2
            assert all(r.status == "failed" for r in rows)

    def test_default_category_fallback(self, crawler_db, fake_process_task, upload_dir, db):
        """tagger 未打标时按站点默认分类映射（树莓派站点 → 树莓派分类）。"""
        with session_scope() as s:
            # 用真实站点 code：DEFAULT_CATEGORY_BY_SITE 按 code 映射默认分类
            repo.sync_sites(s, [SiteConfig(
                code="raspberrypi_blog", name="树莓派博客", source_type="rss",
                adapter="rss_feed", risk_level="low",
                license_note="测试用", config={"feed_url": "https://x/feed"},
            )])
            site_id = s.query(Site).filter(Site.code == "raspberrypi_blog").first().id
            s.add(_add_crawler_doc(site_id=site_id, url="https://example.com/pi/d1",
                                   text="D5 独特内容：树莓派 GPIO 引脚教程",
                                   category="", relevant=None, is_tagged=False))

        stats = sync_documents(limit=10)
        assert stats.synced == 1
        from app.models.document import Category, Document as KbDocument

        kb_doc = db.query(KbDocument).filter(
            KbDocument.source_url == "https://example.com/pi/d1").first()
        cat = db.query(Category).filter(Category.id == kb_doc.category_id).first()
        assert cat.name == "树莓派"
