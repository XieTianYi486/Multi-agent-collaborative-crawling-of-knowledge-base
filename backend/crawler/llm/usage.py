"""成本账本与预算闸门。

- 每次 LLM 调用按 models.yaml 中的价格估算成本，写入 llm_usage 表；
- ensure_budget 在 LLM 步骤前检查当日累计成本，超预算抛 BudgetExceeded，
  编排器捕获后跳过该步骤（规则管线照常运行）。
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..settings import ModelSpec, get_settings
from ..store import repo


class BudgetExceeded(Exception):
    """当日 LLM 预算已用完。"""


def estimate_cost(spec: ModelSpec, tokens_in: int, tokens_out: int, batch: bool) -> float:
    """按价格表估算单次调用成本（元）；批量接口按半价计。"""
    factor = 0.5 if batch else 1.0
    return (tokens_in * spec.price_in + tokens_out * spec.price_out) / 1_000_000 * factor


def ensure_budget(session: Session, task: str, reserve: float = 0.0) -> None:
    """LLM 调用前的预算闸门。超预算抛 BudgetExceeded。"""
    settings = get_settings()
    spent = repo.daily_cost(session)
    if spent + reserve >= settings.daily_budget_cny:
        raise BudgetExceeded(
            f"任务 {task} 被预算闸门拦截：今日已用 ¥{spent:.4f}，预算 ¥{settings.daily_budget_cny}"
        )


def record_call(
    session: Session,
    *,
    task: str,
    spec: ModelSpec,
    batch: bool,
    tokens_in: int,
    tokens_out: int,
    latency_ms: int,
    status: str = "ok",
) -> None:
    """记账：写入 llm_usage 表。"""
    cost = estimate_cost(spec, tokens_in, tokens_out, batch)
    repo.record_usage(
        session,
        task=task,
        provider=spec.provider,
        model=spec.model,
        batch=batch,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_est=cost,
        latency_ms=latency_ms,
        status=status,
    )
