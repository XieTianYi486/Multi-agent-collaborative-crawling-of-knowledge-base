@echo off
title 人工智能学院教学知识库 - Launcher
cd /d "%~dp0"

echo ============================================
echo   人工智能学院教学知识库 - Starting All
echo ============================================
echo.
echo   Backend:  http://localhost:8001
echo   Frontend: http://localhost:5173
echo   Account:  见 backend\.env 的 ADMIN_USERNAME / ADMIN_PASSWORD（登录需验证码）
echo.

echo Cleaning up old backend process on port 8001...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8001.*LISTENING" 2^>nul') do taskkill /PID %%a /F >nul 2>nul

echo Starting Backend...
REM 注意：不要加 --reload（Windows 下 reloader 检测文件变化后卡死、孤儿 worker 占端口）
start "KB-Backend" cmd /k "cd /d %~dp0backend && set PYTHONIOENCODING=utf-8 && python -m uvicorn app.main:app --host 0.0.0.0 --port 8001"

timeout /t 4 /nobreak >nul

echo Starting Frontend...
start "KB-Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"

echo.
echo Both services started in separate windows.
echo Close the service windows to stop, or close this window.
echo.
pause
