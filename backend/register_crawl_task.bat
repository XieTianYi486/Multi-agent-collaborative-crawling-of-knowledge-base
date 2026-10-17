@echo off
rem ============================================================
rem 注册 Windows 任务计划：每日爬取流水线（采集→智能体处理→入库知识库）
rem 用法：双击或以管理员身份运行（"不管用户是否登录"需管理员）
rem ============================================================

set SCRIPT_DIR=%~dp0

rem 定位 Python 解释器（优先环境变量中能找到的 python）
set "PYTHON_EXE="
for /f "delims=" %%i in ('where python 2^>nul') do if not defined PYTHON_EXE set "PYTHON_EXE=%%i"
if not defined PYTHON_EXE set "PYTHON_EXE=python"

echo 使用 Python: %PYTHON_EXE%
echo 使用脚本: %SCRIPT_DIR%run_crawl_daily.py

schtasks /Create /F /TN "ESP32KBCrawlerDaily" /SC DAILY /ST 08:30 ^
  /TR "\"%PYTHON_EXE%\" \"%SCRIPT_DIR%run_crawl_daily.py\""

echo.
echo 任务已注册：ESP32KBCrawlerDaily（每天 08:30）
echo 查看：schtasks /Query /TN ESP32KBCrawlerDaily
echo 手动运行一次：schtasks /Run /TN ESP32KBCrawlerDaily
echo 删除：schtasks /Delete /TN ESP32KBCrawlerDaily /F
echo.
echo 注意：
echo   1. run_crawl_daily.py 启动时自动切换工作目录到 backend/，任务计划无需配置起始目录；
echo   2. 建议低峰时段运行——爬虫进程与 uvicorn 共用 ChromaDB，并发写有锁竞争风险；
echo   3. 首轮大批量回填建议先停 uvicorn 再手动跑一次 run_crawl_daily.py。
pause
