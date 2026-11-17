# ============================================================
# 定向补采安全与闭环测试
# 覆盖：robots.txt fail-closed 语义、公网地址防护（防 SSRF）、
#       重复内容返回既有文档（补采需求仍可闭环）
# ============================================================

import httpx
import pytest

from crawler.crawl import robots
from crawler.crawl.targeted import _is_public_host
from crawler.settings import SiteConfig
from crawler.store import db as cdb
from crawler.store import repo
from crawler.store.db import session_scope
from crawler.store.models import Document, Site


@pytest.fixture()
def crawler_db():
    """初始化爬虫测试库（KB_DATA_DIR 已被 conftest 指向测试目录）。"""
    cdb.init_db()
    return cdb


def _client(handler) -> httpx.Client:
    return httpx.Client(
        transport=httpx.MockTransport(handler), follow_redirects=True,
    )


class TestRobots:
    def test_5xx_fails_closed(self):
        """robots.txt 5xx 必须按拒绝处理（RFC 9309），且失败缓存有 TTL"""
        robots._cache.clear()

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, request=request)

        with _client(handler) as http:
            assert robots.is_allowed(http, "https://example.com/a") is False

    def test_404_allows(self):
        """4xx = 站点没有 robots.txt → 允许抓取"""
        robots._cache.clear()

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, request=request)

        with _client(handler) as http:
            assert robots.is_allowed(http, "https://example.com/a") is True

    def test_network_error_fails_closed(self):
        robots._cache.clear()

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("boom", request=request)

        with _client(handler) as http:
            assert robots.is_allowed(http, "https://example.com/a") is False

    def test_explicit_disallow_respected(self):
        robots._cache.clear()
        body = "User-agent: *\nDisallow: /private\nAllow: /\n"

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=body, request=request)

        with _client(handler) as http:
            assert robots.is_allowed(http, "https://example.com/private/x") is False
            assert robots.is_allowed(http, "https://example.com/public/x") is True

    def test_non_http_scheme_rejected(self):
        robots._cache.clear()
        with _client(lambda r: httpx.Response(200, request=r)) as http:
            assert robots.is_allowed(http, "ftp://example.com/a") is False
            assert robots.is_allowed(http, "file:///etc/passwd") is False


class TestPublicHostGuard:
    def test_private_and_loopback_blocked(self):
        assert _is_public_host("127.0.0.1") is False
        assert _is_public_host("localhost") is False
        assert _is_public_host("10.0.0.1") is False
        assert _is_public_host("192.168.1.1") is False
        assert _is_public_host("172.16.0.1") is False
        assert _is_public_host("169.254.169.254") is False  # 云元数据地址
        assert _is_public_host("::1") is False
        assert _is_public_host("") is False

    def test_public_ip_allowed(self):
        assert _is_public_host("8.8.8.8") is True
        assert _is_public_host("1.1.1.1") is True


class TestIngestReturnExisting:
    def test_content_duplicate_returns_existing(self, crawler_db):
        """重复内容在 return_existing=True 时返回既有文档，补采可据此闭环"""
        from crawler.crawl.crawl import ingest_item
        from crawler.crawl.dedup import content_hash

        with session_scope() as s:
            repo.sync_sites(s, [SiteConfig(
                code="dup_site", name="去重站点", source_type="rss",
                adapter="rss_feed", risk_level="low",
                license_note="测试用", config={"feed_url": "https://x/feed"},
            )])
            site = s.query(Site).filter(Site.code == "dup_site").first()

            from crawler.crawl.adapters.base import RawItem

            text = f"独特去重内容 {content_hash('x')[:8]}"
            first = ingest_item(s, site, RawItem(
                url="https://example.com/dup/1",
                title="原文", content_text=text,
            ))
            assert first is not None

            # 相同内容、不同 URL → 默认 None（重复），return_existing 返回原文
            dup = ingest_item(s, site, RawItem(
                url="https://example.com/dup/2",
                title="转载", content_text=text,
            ))
            assert dup is None
            existing = ingest_item(s, site, RawItem(
                url="https://example.com/dup/3",
                title="再转载", content_text=text,
            ), return_existing=True)
            assert existing is not None
            assert existing.id == first.id

            # 确认没有新增行
            count = s.query(Document).filter(
                Document.content_hash == first.content_hash,
            ).count()
            assert count == 1

            # 清理：不写 kb_syncs 留痕，避免污染后续 sync_documents 用例的全局计数
            s.delete(first)
            s.delete(site)
            s.commit()
