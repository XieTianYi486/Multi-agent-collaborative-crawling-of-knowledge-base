# ============================================================
# 适配器测试：httpx MockTransport 假数据驱动，不触网
# ============================================================

import base64
import json
from types import SimpleNamespace

import httpx

from crawler.crawl.adapters import espressif_docs, github, html_list, rss_feed, sitemap

LIST_HTML = """
<html><body>
<a href="/topic/1.html">ESP32 入门</a>
<a href="/topic/2.html">蓝牙教程</a>
<a href="/topic/1.html">重复链接</a>
<a href="#anchor">锚点</a>
</body></html>
"""


def _site(**cfg):
    return SimpleNamespace(
        code="t", rate_limit=0, base_url="https://t.example.com",
        config_json=cfg, adapter="",
    )


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


def _html(text, url="https://t.example.com/list"):
    return httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"},
                          text=text, request=httpx.Request("GET", url))


class TestHtmlList:
    def test_list_mode(self):
        def handler(req):
            return _html(LIST_HTML)

        site = _site(list_url="https://t.example.com/list", link_selector="a")
        items = html_list.fetch(site, _client(handler))
        urls = [i.url for i in items]
        assert "https://t.example.com/topic/1.html" in urls
        assert "https://t.example.com/topic/2.html" in urls
        # 锚点链接被过滤
        assert not any("#" in u for u in urls)
        # 列表页本身不采集（选择器只命中 a，详情页也有 a…… 这里只断言关键项）
        assert len(items) >= 2

    def test_tree_mode_collects_sub_links(self):
        def handler(req):
            if "list" in req.url.path:
                return _html(LIST_HTML)
            return _html(
                '<html><body><a href="/leaf.html">叶子页</a></body></html>',
                url=str(req.url),
            )

        site = _site(list_url="https://t.example.com/list", link_selector="a", mode="tree")
        items = html_list.fetch(site, _client(handler))
        urls = [i.url for i in items]
        # 子链接（叶子页）优先排在前面
        assert urls[0] == "https://t.example.com/leaf.html"

    def test_exclude_and_max_items(self):
        def handler(req):
            return _html(LIST_HTML)

        site = _site(list_url="https://t.example.com/list", link_selector="a",
                     max_items=1, exclude=["/topic/2"])
        items = html_list.fetch(site, _client(handler))
        assert len(items) == 1
        assert "topic/2" not in items[0].url


class TestRssFeed:
    RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>t</title>
<item><title>ESP32 v5.3 发布</title><link>https://t.example.com/a</link>
<description>&lt;p&gt;支持新芯片&lt;/p&gt;</description></item>
<item><title>无链接条目</title></item>
</channel></rss>
"""

    def test_parse_entries(self):
        def handler(req):
            return httpx.Response(200, content=self.RSS.encode("utf-8"),
                                  request=req)

        site = _site(feed_url="https://t.example.com/feed")
        items = rss_feed.fetch(site, _client(handler))
        assert len(items) == 1  # 无链接条目被跳过
        assert items[0].url == "https://t.example.com/a"
        assert items[0].title == "ESP32 v5.3 发布"
        assert items[0].content_html


class TestSitemap:
    SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>https://t.example.com/zh-hans/a</loc></url>
<url><loc>https://t.example.com/en/b</loc></url>
<url><loc>https://t.example.com/zh-hans/file.pdf</loc></url>
</urlset>
"""

    def test_prefix_filter_and_html_only(self):
        def handler(req):
            if "sitemap" in req.url.path:
                return httpx.Response(200, content=self.SITEMAP.encode("utf-8"),
                                      request=req)
            if req.url.path.endswith(".pdf"):
                return httpx.Response(200, content=b"%PDF-1.4",
                                      headers={"content-type": "application/pdf"},
                                      request=req)
            return _html("<html><title>页面</title>正文内容</html>", url=str(req.url))

        site = _site(sitemap_url="https://t.example.com/sitemap.xml",
                     path_prefix="/zh-hans/", max_items=10)
        items = sitemap.fetch(site, _client(handler))
        urls = [i.url for i in items]
        # 只保留 /zh-hans/ 前缀的 HTML 页（en 前缀与 PDF 被过滤）
        assert "https://t.example.com/zh-hans/a" in urls
        assert not any("/en/" in u for u in urls)
        assert not any(u.endswith(".pdf") for u in urls)


class TestGithubRepo:
    def test_repo_mode_metadata_releases_readme(self):
        def handler(req):
            path = req.url.path
            if path == "/repos/espressif/esp-idf":
                return httpx.Response(200, json={
                    "description": "ESP-IDF 框架", "html_url": "https://github.com/espressif/esp-idf",
                    "language": "C", "topics": ["esp32"], "stargazers_count": 100,
                    "license": {"spdx_id": "Apache-2.0"}, "created_at": "2018-01-01T00:00:00Z",
                }, request=req)
            if path.endswith("/releases"):
                return httpx.Response(200, json=[
                    {"tag_name": "v5.3", "name": "v5.3", "body": "支持 ESP32-C6",
                     "html_url": "https://github.com/espressif/esp-idf/releases/tag/v5.3",
                     "published_at": "2024-01-01T00:00:00Z"},
                ], request=req)
            if path.endswith("/readme"):
                content = base64.b64encode("# ESP-IDF\n官方文档".encode("utf-8")).decode("ascii")
                return httpx.Response(200, json={"content": content}, request=req)
            return httpx.Response(404, request=req)

        site = _site(mode="repo", owner="espressif", repo="esp-idf", releases=5)
        items = github.fetch(site, _client(handler))
        assert len(items) == 3  # 元数据 + 1 条 release + README
        kinds = [i.meta.get("type", "meta") for i in items]
        assert "release" in kinds
        assert "readme" in kinds
        release = next(i for i in items if i.meta.get("type") == "release")
        assert "ESP32-C6" in release.content_text

    def test_repo_404_returns_empty(self):
        def handler(req):
            return httpx.Response(404, request=req)

        site = _site(mode="repo", owner="x", repo="y")
        assert github.fetch(site, _client(handler)) == []


class TestEspressifDocs:
    PAGE_WITH_LINKS = """
<html><script>
var docs = ["https://documentation.espressif.com/doc/a", "https://documentation.espressif.com/doc/b"];
</script><body>文档门户</body></html>
"""

    def test_extracts_doc_links_from_page(self):
        def handler(req):
            if "documentList" in req.url.path:
                return _html(self.PAGE_WITH_LINKS, url="https://documentation.espressif.com/zh/documentList")
            return _html("<html><title>文档页</title>ESP32 配置指南</html>", url=str(req.url))

        site = _site(list_url="https://documentation.espressif.com/zh/documentList",
                     max_items=10)
        items = espressif_docs.fetch(site, _client(handler))
        urls = [i.url for i in items]
        assert "https://documentation.espressif.com/doc/a" in urls
        assert "https://documentation.espressif.com/doc/b" in urls

    def test_no_links_and_api_probe_fails_returns_empty(self):
        def handler(req):
            return _html("<html><body>空页面</body></html>", url=str(req.url))

        site = _site(list_url="https://documentation.espressif.com/zh/documentList",
                     api_candidates=["https://documentation.espressif.com/api/x"])
        assert espressif_docs.fetch(site, _client(handler)) == []

    def test_json_extraction(self):
        data = {"items": [{"url": "https://documentation.espressif.com/doc/z"}],
                "nested": ["https://documentation.espressif.com/doc/y"]}
        urls = espressif_docs._extract_urls_from_json(data, "https://documentation.espressif.com")
        assert "https://documentation.espressif.com/doc/z" in urls
        assert "https://documentation.espressif.com/doc/y" in urls
