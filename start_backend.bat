@echo off
title AI Academy KB Backend
cd /d "%~dp0backend"

echo ============================================
echo   人工智能学院教学知识库 - Backend
echo ============================================
echo.

if not exist ".env" (
    echo [WARN] .env not found, copying from .env.example...
    copy .env.example .env >nul
    echo [INFO] Please edit backend\.env with your Bailian API Key
    pause
    exit /b 1
)

if not exist "data" mkdir data
if not exist "uploads" mkdir uploads

echo [1/2] Installing Python dependencies...
pip install -r requirements.txt -q 2>nul

echo [2/2] Starting FastAPI on port 8001...
echo.
echo   API Docs: http://localhost:8001/docs
echo   Account:  admin / admin123
echo   Press Ctrl+C to stop
echo.

set PYTHONIOENCODING=utf-8
REM 注意：本机不要加 --reload（Windows 下 reloader 检测到文件变化后会卡死，
REM 旧 worker 不退出、新代码不生效，请求全部挂起）。改代码后手动重启本脚本。
python -m uvicorn app.main:app --host 0.0.0.0 --port 8001

pause
