# ============================================================
# 每日爬取流水线入口（Windows 任务计划程序调用）
#
# 任务计划程序配置示例：
#   程序：<backend>\.venv\Scripts\python.exe
#   参数：E:\Claude_Project_second\Multi-agent collaborative crawling of knowledge base\backend\run_crawl_daily.py
#   起始于：<backend>\（重要：app.* 依赖 .env 的 cwd 约定）
#   建议时间：每天 08:30（避开整点；爬虫进程与 uvicorn 共用 ChromaDB，
#             低峰运行避免写锁竞争）
#
# 手工运行：cd backend && python run_crawl_daily.py
#           （可加 --site <code> 只采指定站点调试，可重复传多次）
# ============================================================

import argparse
import io
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# 未安装为包时也能直接运行（backend/ 加入 sys.path，app.* 与 crawler.* 都可用）
BACKEND_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_DIR))
# 切换到 backend/：app.core.config 的 .env 与相对路径都依赖 cwd
# （Windows 任务计划无法可靠设置起始目录，这里兜底）
os.chdir(str(BACKEND_DIR))

from crawler.pipeline import run_daily  # noqa: E402

# Windows 控制台 GBK 编码兼容
# 注意：不能在 pytest 捕获模式下包装（其 stdout 无真实 buffer，
# 包装会导致捕获文件被关闭、pytest 退出时崩溃），需容错跳过
if sys.platform == "win32":
    for _stream_name in ("stdout", "stderr"):
        _stream = getattr(sys, _stream_name)
        if (getattr(_stream, "encoding", "") or "").lower() != "utf-8" \
                and hasattr(_stream, "buffer"):
            try:
                setattr(sys, _stream_name,
                        io.TextIOWrapper(_stream.buffer, encoding="utf-8", errors="replace"))
            except Exception:
                pass

LOG_DIR = BACKEND_DIR / "logs"


def _setup_logging() -> None:
    """日志：控制台 + 每日文件（backend/logs/crawler_YYYYMMDD.log）。"""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / f"crawler_{datetime.now():%Y%m%d}.log"
    handlers = [
        logging.StreamHandler(),
        logging.FileHandler(log_file, encoding="utf-8"),
    ]
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )


def main() -> int:
    _setup_logging()
    parser = argparse.ArgumentParser(description="每日爬取流水线（采集→打标→审核→摘要→入库知识库）")
    parser.add_argument("--site", action="append", dest="site_codes",
                        help="只采集指定站点 code（可重复传多次，调试用）")
    args = parser.parse_args()

    logging.getLogger("crawler").info("===== 每日爬取流水线开始 =====")

    # 先触发知识库主库建表/迁移（source_url/source_hash 列），
    # 否则首轮入库会因缺列失败
    from app.db.sqlite import init_db as kb_init_db

    kb_init_db()

    results = run_daily({"site_codes": args.site_codes} if args.site_codes else None)

    failed = [r.name for r in results.values() if not r.ok and not r.skipped]
    for name, r in results.items():
        if r.ok:
            state = "完成"
        elif r.skipped:
            state = "跳过（预算/LLM不可用）"
        else:
            state = "失败"
        print(f"[{state}] {name} ({r.duration_ms}ms)")
        if not r.ok and not r.skipped:
            print(f"       错误: {r.error}")

    logging.getLogger("crawler").info(
        "===== 每日爬取流水线结束（%s）=====",
        "失败" if failed else "成功",
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
