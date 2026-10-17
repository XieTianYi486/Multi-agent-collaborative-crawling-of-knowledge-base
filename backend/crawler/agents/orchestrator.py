"""轻量 DAG 编排器（~100 行）。

选型理由：
- 本项目是批处理流水线而非对话式多 Agent 协作——步骤确定、依赖简单，
  一个带依赖/重试/跳过的任务列表即可覆盖；
- 教学可维护性：学生读这一个文件就能理解全系统编排；
- 内建预算语义：LLM 步骤抛 BudgetExceeded 时标记 skipped，规则管线照常运行。

未来若出现真正的多 Agent 交互（分工、辩论、人工审批），再引入 LangGraph 封装。
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Callable

from ..llm.usage import BudgetExceeded

log = logging.getLogger(__name__)


@dataclass
class Step:
    """流水线步骤。

    - deps: 依赖步骤名（全部执行完才执行本步）；
    - retries: 失败重试次数（指数退避 2^n 秒）；
    - optional: True 时失败不阻断流水线（LLM 步骤均应 optional）。
    """

    name: str
    func: Callable[[dict], Any]
    deps: tuple[str, ...] = ()
    retries: int = 1
    optional: bool = False


@dataclass
class StepResult:
    name: str
    ok: bool
    skipped: bool = False
    error: str = ""
    duration_ms: int = 0


class Orchestrator:
    def __init__(self, steps: list[Step]):
        self.steps = steps

    def run(
        self,
        context: dict | None = None,
        on_step_done: Callable[[str, "StepResult"], Any] | None = None,
    ) -> dict[str, StepResult]:
        """执行流水线。on_step_done 每步完成后回调 (步骤名, 结果)——用于 UI 实时状态。"""
        # 注意：不能用 `context or {}` —— 空 dict 是合法输入，且步骤间靠它共享状态
        context = {} if context is None else context
        results: dict[str, StepResult] = {}
        pending = list(self.steps)

        while pending:
            ready = [s for s in pending if all(d in results for d in s.deps)]
            if not ready:
                missing = sorted({d for s in pending for d in s.deps if d not in results})
                raise RuntimeError(f"步骤依赖缺失或存在环: {missing}")
            for step in ready:
                result = self._run_step(step, context)
                results[step.name] = result
                if on_step_done is not None:
                    on_step_done(step.name, result)
            pending = [s for s in pending if s.name not in results]

        return results

    def _run_step(self, step: Step, context: dict) -> StepResult:
        start = time.monotonic()
        attempt = 0
        while True:
            attempt += 1
            try:
                step.func(context)
                return StepResult(
                    name=step.name,
                    ok=True,
                    duration_ms=int((time.monotonic() - start) * 1000),
                )
            except BudgetExceeded as exc:
                log.warning("步骤 %s 被预算闸门跳过: %s", step.name, exc)
                return StepResult(name=step.name, ok=False, skipped=True, error=str(exc))
            except Exception as exc:  # noqa: BLE001
                if attempt <= step.retries:
                    backoff = 2 ** attempt
                    log.warning("步骤 %s 失败（第 %d 次），%d 秒后重试: %s",
                                step.name, attempt, backoff, exc)
                    time.sleep(backoff)
                    continue
                if step.optional:
                    log.warning("步骤 %s（可选）失败，继续流水线: %s", step.name, exc)
                else:
                    log.error("步骤 %s 失败: %s", step.name, exc)
                return StepResult(
                    name=step.name,
                    ok=False,
                    error=f"{type(exc).__name__}: {exc}",
                    duration_ms=int((time.monotonic() - start) * 1000),
                )
