# ============================================================
# 爬虫去重纯函数测试：URL 规范化 / 内容哈希 / SimHash 近重复
# ============================================================

from crawler.crawl.dedup import (
    content_hash,
    hamming_distance,
    is_near_dup,
    normalize_url,
    simhash64,
    url_hash,
)


class TestNormalizeUrl:
    def test_removes_fragment(self):
        assert normalize_url("https://a.com/x#sec") == "https://a.com/x"

    def test_trailing_slash(self):
        assert normalize_url("https://a.com/x/") == normalize_url("https://a.com/x")

    def test_lowercase_host(self):
        assert normalize_url("HTTPS://A.Com/x") == "https://a.com/x"

    def test_keeps_query(self):
        assert normalize_url("https://a.com/x?a=1") == "https://a.com/x?a=1"


class TestHashes:
    def test_url_hash_dedup_equivalence(self):
        assert url_hash("https://a.com/x#f") == url_hash("https://a.com/x")

    def test_content_hash_whitespace_insensitive(self):
        # 多空格/首尾空白归一化后等价（\n 会被替换成空格，属于设计行为）
        assert content_hash("ESP32  开发板") == content_hash(" ESP32 开发板 ")
        assert content_hash("ESP32\n开发板") == content_hash("ESP32 开发板")

    def test_content_hash_differs(self):
        assert content_hash("ESP32 教程") != content_hash("树莓派 教程")


class TestSimhash:
    def test_identical_text_distance_zero(self):
        a = simhash64("ESP32 开发板入门教程：LED 闪烁")
        b = simhash64("ESP32 开发板入门教程：LED 闪烁")
        assert hamming_distance(a, b) == 0

    def test_very_different_text_large_distance(self):
        a = simhash64("ESP32 蓝牙 开发板 教程")
        b = simhash64("股票 行情 分析 投资 理财 基金 涨停")
        assert hamming_distance(a, b) > 10

    def test_empty_hash_never_near_dup(self):
        assert not is_near_dup("", "0" * 16)

    def test_threshold(self):
        a = simhash64("ESP32 教程 蓝牙")
        b = simhash64("ESP32 教程 蓝牙")
        assert is_near_dup(a, b, threshold=3)
        assert not is_near_dup(a, b, threshold=-1)
