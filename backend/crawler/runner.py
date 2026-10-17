"""流水线运行器：后台线程执行 + 进程内运行状态（供 FastAPI 爬取中心查询）。

与 uvicorn 同进程运行时的并发注意：
- 同一时刻只允许一个流水线实例（start_run 幂等拒绝）；
- 爬虫进程与 API 服务共用 ChromaDB 持久目录，入库阶段有写锁竞争，
  页面手动触发时建议在低峰时段。
"""
from __future__ import annotations

import logging
import threading
from typing import Optional

from .pipeline import run_daily
from .timeutil import utcnow

log = logging.getLogger(__name__)

_lock = threading.Lock()

# 最近一次运行结果（含进行中状态）
_run_state: dict = {
    "running": False,
    "trigger": "",          # manual / scheduled
    "started_at": None,
    "finished_at": None,
    "error": "",
    "step_results": {},     # {step_name: {ok, skipped, error, duration_ms}}
}


def _snapshot() -> dict:
    """返回当前运行状态快照（深拷贝 step_results，避免并发写读冲突）。"""
    with _lock:
        return {
            "running": _run_state["running"],
            "trigger": _run_state["trigger"],
            "started_at": _run_state["started_at"],
            "finished_at": _run_state["finished_at"],
            "error": _run_state["error"],
            "step_results": dict(_run_state["step_results"]),
        }


def start_run(trigger: str = "manual") -> bool:
    """启动流水线（后台 daemon 线程）。已在运行时返回 False（不重复启动）。"""
    global _run_state
    with _lock:
        if _run_state["running"]:
            log.warning("流水线已在运行中，忽略新的触发（%s）", trigger)
            return False
        _run_state = {
            "running": True,
            "trigger": trigger,
            "started_at": utcnow(),
            "finished_at": None,
            "error": "",
            "step_results": {},
        }

    def _on_step(step_name: str, result) -> None:
        with _lock:
            _run_state["step_results"][step_name] = {
                "ok": result.ok,
                "skipped": result.skipped,
                "error": result.error,
                "duration_ms": result.duration_ms,
            }

    def _target() -> None:
        try:
            results = run_daily(on_step=_on_step)
            failed = [n for n, r in results.items() if not r.ok and not r.skipped]
            with _lock:
                _run_state["error"] = "；".join(f"{n}: {r.error}" for n, r in results.items()
                                               if not r.ok and not r.skipped)[:2000]
                _run_state["failed_steps"] = failed
            log.info("流水线完成：%s",
                     "成功" if not failed else f"失败步骤 {failed}")
        except Exception as exc:  # noqa: BLE001 - 记录错误，不让线程静默死掉
            with _lock:
                _run_state["error"] = f"{type(exc).__name__}: {exc}"
            log.exception("流水线运行异常")
        finally:
            with _lock:
                _run_state["running"] = False
                _run_state["finished_at"] = utcnow()

    thread = threading.Thread(target=_target, daemon=True, name="crawler-pipeline")
    thread.start()
    log.info("流水线已启动（trigger=%s）", trigger)
    return True


def get_run_state() -> dict:
    return _snapshot()
