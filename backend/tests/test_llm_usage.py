# ============================================================
# LLM 成本账本测试：估价 / 预算闸门 / 记账落库
# ============================================================

import pytest

from crawler.llm.usage import BudgetExceeded, ensure_budget, estimate_cost, record_call
from crawler.settings import ModelSpec
from crawler.store import db as cdb
from crawler.store import repo
from crawler.store.db import session_scope
from crawler.store.models import LlmUsage


def _spec(price_in=1.0, price_out=2.0) -> ModelSpec:
    return ModelSpec(model="qwen-flash", price_in=price_in, price_out=price_out)


class TestEstimateCost:
    def test_normal_pricing(self):
        cost = estimate_cost(_spec(), tokens_in=1_000_000, tokens_out=500_000, batch=False)
        assert cost == pytest.approx(1.0 + 1.0)  # 100万入 ×1元 + 50万出 ×2元 = 2元

    def test_batch_half_price(self):
        cost = estimate_cost(_spec(), tokens_in=1_000_000, tokens_out=0, batch=True)
        assert cost == pytest.approx(0.5)


class TestBudgetGate:
    def test_under_budget_passes(self, monkeypatch):
        monkeypatch.setattr(repo, "daily_cost", lambda session: 1.0)
        ensure_budget(object(), "tagger")  # 1.0 < 2.0，不抛异常

    def test_over_budget_raises(self, monkeypatch):
        monkeypatch.setattr(repo, "daily_cost", lambda session: 2.5)
        with pytest.raises(BudgetExceeded):
            ensure_budget(object(), "tagger")


class TestRecordCall:
    def test_records_usage_row(self):
        cdb.init_db()
        import uuid

        task = f"tagger_{uuid.uuid4().hex[:6]}"  # 唯一任务名，规避同库其他用例的残留行
        with session_scope() as s:
            record_call(s, task=task, spec=_spec(), batch=True,
                        tokens_in=1000, tokens_out=100, latency_ms=50)
            rows = s.query(LlmUsage).filter(LlmUsage.task == task).all()
            assert len(rows) == 1
            row = rows[0]
            assert row.batch is True
            assert row.tokens_in == 1000
            assert row.cost_est == pytest.approx((1000 * 1.0 + 100 * 2.0) / 1_000_000 * 0.5)

    def test_daily_cost_sum(self):
        cdb.init_db()
        with session_scope() as s:
            baseline = repo.daily_cost(s)  # 其他用例可能已记账，取增量对比
            record_call(s, task="tagger", spec=_spec(), batch=False,
                        tokens_in=100_000, tokens_out=0, latency_ms=0)
            record_call(s, task="reviewer", spec=_spec(), batch=False,
                        tokens_in=200_000, tokens_out=0, latency_ms=0)
            assert repo.daily_cost(s) - baseline == pytest.approx(0.1 + 0.2)
