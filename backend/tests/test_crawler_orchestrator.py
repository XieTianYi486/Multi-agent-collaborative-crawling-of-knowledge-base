# ============================================================
# DAG 编排器测试：依赖顺序 / 重试退避 / optional / 预算跳过 / 环检测
# ============================================================

import pytest

from crawler.agents.orchestrator import Orchestrator, Step
from crawler.llm.usage import BudgetExceeded


class TestTopology:
    def test_deps_execute_in_order(self):
        order = []

        def make(name):
            def fn(ctx):
                order.append(name)
                ctx[name] = True
            return fn

        steps = [
            Step("a", make("a")),
            Step("b", make("b"), deps=("a",)),
            Step("c", make("c"), deps=("a", "b")),
        ]
        results = Orchestrator(steps).run()
        assert order == ["a", "b", "c"]
        assert all(r.ok for r in results.values())

    def test_shared_context(self):
        steps = [
            Step("produce", lambda ctx: ctx.update({"x": 42})),
            Step("consume", lambda ctx: ctx.update({"got": ctx["x"]}), deps=("produce",)),
        ]
        results = Orchestrator(steps).run()
        assert results["consume"].ok

    def test_missing_dep_raises(self):
        steps = [Step("a", lambda ctx: None, deps=("nonexistent",))]
        with pytest.raises(RuntimeError, match="依赖缺失"):
            Orchestrator(steps).run()

    def test_cycle_raises(self):
        steps = [
            Step("a", lambda ctx: None, deps=("b",)),
            Step("b", lambda ctx: None, deps=("a",)),
        ]
        with pytest.raises(RuntimeError):
            Orchestrator(steps).run()


class TestRetry:
    def test_retry_then_success(self, monkeypatch):
        attempts = {"n": 0}
        slept = []
        monkeypatch.setattr("crawler.agents.orchestrator.time.sleep", lambda s: slept.append(s))

        def flaky(ctx):
            attempts["n"] += 1
            if attempts["n"] < 2:
                raise ValueError("临时失败")

        steps = [Step("flaky", flaky, retries=2)]
        results = Orchestrator(steps).run()
        assert results["flaky"].ok
        assert attempts["n"] == 2
        assert slept == [2]  # 第一次重试退避 2^1 秒


class TestOptionalAndBudget:
    def test_optional_failure_does_not_block(self):
        def broken(ctx):
            raise ValueError("LLM 挂了")

        steps = [
            Step("required", lambda ctx: None),
            Step("optional_llm", broken, deps=("required",), optional=True),
            Step("after", lambda ctx: None, deps=("optional_llm",)),
        ]
        results = Orchestrator(steps).run()
        assert results["required"].ok
        assert not results["optional_llm"].ok
        assert not results["optional_llm"].skipped
        assert results["after"].ok  # optional 失败仍视为已完成，下游继续

    def test_budget_exceeded_marks_skipped(self):
        def over_budget(ctx):
            raise BudgetExceeded("超预算")

        steps = [
            Step("llm_step", over_budget),
            Step("kb_sync", lambda ctx: None, deps=("llm_step",)),
        ]
        results = Orchestrator(steps).run()
        assert results["llm_step"].skipped
        assert not results["llm_step"].ok
        assert results["kb_sync"].ok  # skipped 也视为已完成，规则管线继续

    def test_required_failure_reported(self):
        steps = [Step("must", lambda ctx: (_ for _ in ()).throw(RuntimeError("boom")), retries=0)]
        results = Orchestrator(steps).run()
        assert not results["must"].ok
        assert "boom" in results["must"].error
