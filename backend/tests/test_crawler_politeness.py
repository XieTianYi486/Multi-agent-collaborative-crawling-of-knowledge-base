# ============================================================
# 采集礼貌性测试：站点限速 + 连续失败熔断
# ============================================================

from datetime import timedelta
from types import SimpleNamespace

from crawler.crawl import politeness
from crawler.timeutil import utcnow


def _fake_site(**kwargs):
    defaults = dict(
        code="test_site",
        consecutive_failures=0,
        breaker_until=None,
        last_crawled_at=None,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


class TestRateLimit:
    def test_first_request_no_wait(self, monkeypatch):
        slept = []
        monkeypatch.setattr(politeness.time, "sleep", lambda s: slept.append(s))
        politeness.wait_before_request("site_a", 1.0)
        assert slept == []

    def test_second_request_waits(self, monkeypatch):
        slept = []
        monkeypatch.setattr(politeness.time, "sleep", lambda s: slept.append(s))
        politeness.wait_before_request("site_b", 1.0)
        politeness.wait_before_request("site_b", 1.0)
        assert len(slept) == 1
        assert 0 < slept[0] <= 1.0


class TestCircuitBreaker:
    def test_no_breaker_initially(self):
        site = _fake_site()
        assert not politeness.is_circuit_open(site)

    def test_breaker_after_three_failures(self):
        site = _fake_site()
        for _ in range(politeness.BREAKER_FAILURES):
            politeness.record_site_failure(site)
        assert politeness.is_circuit_open(site)
        assert site.breaker_until > utcnow()

    def test_breaker_counts_reset_after_trip(self):
        site = _fake_site()
        for _ in range(politeness.BREAKER_FAILURES):
            politeness.record_site_failure(site)
        assert site.consecutive_failures == 0  # 熔断后重置计数

    def test_expired_breaker_closes(self):
        site = _fake_site(breaker_until=utcnow() - timedelta(hours=1))
        assert not politeness.is_circuit_open(site)

    def test_success_resets_failures(self):
        site = _fake_site(consecutive_failures=2)
        politeness.record_site_success(site)
        assert site.consecutive_failures == 0
        assert site.last_crawled_at is not None
