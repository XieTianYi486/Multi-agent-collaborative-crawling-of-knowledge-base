"""跨进程流水线互斥锁（文件锁，Windows / Linux 通用，无第三方依赖）。

背景：Windows 任务计划（独立进程）与管理后台手动触发（uvicorn 进程）可能同时跑流水线，
进程内 threading.Lock 管不住这种并发——两个进程会同时入库同一批爬虫文档，
产生重复 KB 文档与向量分块。

实现：O_CREAT|O_EXCL 原子创建锁文件；进程崩溃遗留的锁按时间戳判定过期后自动破除。
锁文件位于 crawler/data/run.lock（运行期数据目录，不随仓库分发）。
"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path

from .settings import DATA_DIR

log = logging.getLogger(__name__)

LOCK_PATH = Path(DATA_DIR) / "run.lock"
# 流水线单轮通常 <1 小时；超过 3 小时视为进程异常退出遗留的死锁
STALE_SECONDS = 3 * 3600


class PipelineLock:
    """流水线互斥锁：acquire 成功才允许运行；release 释放。"""

    def __init__(self, path: Path = LOCK_PATH):
        self.path = path
        self._held = False

    def acquire(self) -> bool:
        """尝试获取锁。已在运行/锁被他人持有时返回 False。"""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(
                str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY
            )
            os.write(fd, f"pid={os.getpid()} ts={time.time()}".encode())
            os.close(fd)
            self._held = True
            return True
        except FileExistsError:
            if self._is_stale():
                log.warning("检测到过期流水线锁 %s，自动破除", self.path)
                try:
                    self.path.unlink()
                    return self.acquire()
                except OSError:
                    return False
            log.warning(
                "流水线锁被其他进程持有（%s）。如确认没有流水线在运行，"
                "可手动删除该文件后重试。", self.path,
            )
            return False

    def _is_stale(self) -> bool:
        try:
            age = time.time() - self.path.stat().st_mtime
            return age > STALE_SECONDS
        except OSError:
            return True

    def release(self) -> None:
        if not self._held:
            return
        self._held = False
        try:
            self.path.unlink()
        except OSError:
            pass


# 进程内共享单例（线程安全由调用方的 threading.Lock 保证）
pipeline_lock = PipelineLock()
