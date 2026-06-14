@echo off
chcp 65001 >nul
title ACS 资料采集助手 v1.1.0-discovery

:: ── Set project root ──
cd /d "%~dp0"

echo.
echo ╔══════════════════════════════════════════╗
echo ║   ACS 资料采集助手                        ║
echo ║   v1.1.0-discovery 安全测试模式            ║
echo ╚══════════════════════════════════════════╝
echo.

:: ── Check Python ──
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python。请先安装 Python 3.10+ : https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

:: ── Check dependencies ──
python -c "import flask" >nul 2>nul
if %errorlevel% neq 0 (
    echo [提示] 未安装 Flask，正在安装...
    python -m pip install flask --quiet
    if %errorlevel% neq 0 (
        echo [错误] Flask 安装失败，请手动运行: pip install flask
        pause
        exit /b 1
    )
)

:: ── Check port 5020 ──
python -c "from acs.web.server_launcher import check_port; import sys; sys.exit(0 if check_port(5020) else 1)" >nul 2>nul
if %errorlevel% neq 0 (
    echo [提示] 端口 5020 已被占用，可能已有服务在运行。
    echo.
    choice /c yn /m "是否尝试继续启动？[Y=是 N=否]"
    if errorlevel 2 exit /b 1
)

:: ── Start server ──
echo [启动] 正在启动本地服务 127.0.0.1:5020 ...
echo [模式] ACS_MODE=shadow（安全测试模式）
echo [提示] 请勿关闭本窗口，使用完毕后按 Ctrl+C 退出。
echo.

start "" python -m acs.web.local_server --port 5020 --host 127.0.0.1

:: ── Wait for health ──
echo [等待] 等待服务就绪...
python -c "from acs.web.server_launcher import wait_for_health; ok = wait_for_health('http://127.0.0.1:5020/api/health', timeout=30); print('[就绪] 服务已启动' if ok else '[警告] 服务未在 30 秒内就绪，请检查')"

:: ── Open browser ──
echo [打开] 正在打开 ACS 资料采集助手界面...
python -c "from acs.web.browser_open import open_browser; open_browser('acs_ui/index.html')"

echo.
echo ═══════════════════════════════════════════
echo   ACS 资料采集助手已启动
echo   本地地址: http://127.0.0.1:5020
echo   安全模式: ACS_MODE=shadow
echo   真实生产: 未启用
echo ═══════════════════════════════════════════
echo.
echo 按任意键关闭本窗口（服务将停止）...
pause >nul
