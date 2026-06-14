@echo off
chcp 65001 >nul
title ACS 资料采集助手 v1.1.0-discovery

:: ── Set project root ──
cd /d "%~dp0"

echo.
echo +==========================================+
echo |   ACS 资料采集助手                        |
echo |   v1.1.2-desktop-polish 安全测试模式       |
echo +==========================================+
echo.

:: ── Check Python ──
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] 未找到 Python。请先安装 Python 3.10+ : https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

:: ── Check dependencies ──
python -c "import flask" >nul 2>nul
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] 未安装 Flask 或其他依赖。
    echo.
    echo 请先运行以下命令安装依赖：
    echo   python -m pip install -r requirements.txt
    echo.
    echo 如网络不可用，请手动安装：pip install flask beautifulsoup4 lxml requests
    echo.
    pause
    exit /b 1
)

:: ── Check port 5020 ──
python -c "from acs.web.server_launcher import check_port; import sys; sys.exit(0 if check_port(5020) else 1)" >nul 2>nul
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] 端口 5020 已被占用。
    echo.
    echo 可能有其他程序占用了 5020 端口，或已有 ACS 服务在运行。
    echo 请先关闭占用 5020 端口的程序，再重新启动。
    echo.
    pause
    exit /b 1
)

:: ── Start server ──
echo [启动] 正在启动本地服务 127.0.0.1:5020 ...
echo [模式] ACS_MODE=shadow（安全测试模式）
echo [提示] 请勿关闭本窗口，使用完毕后按 Ctrl+C 退出。
echo.

start "" python -m acs.web.local_server --port 5020 --host 127.0.0.1

:: ── Wait for health ──
echo [WAIT] 等待服务就绪...
python -c "from acs.web.server_launcher import wait_for_health; ok = wait_for_health('http://127.0.0.1:5020/api/health', timeout=30); print('[OK] 服务已启动' if ok else '[WARN] 服务未在 30 秒内就绪，请检查')"

:: ── Open browser ──
echo [OPEN] 正在打开 ACS 资料采集助手界面...
python -c "from acs.web.browser_open import open_browser; open_browser('acs_ui/index.html')"

echo.
echo ==========================================
echo   ACS 资料采集助手已启动
echo   本地地址: http://127.0.0.1:5020
echo   安全模式: ACS_MODE=shadow
echo   真实生产: 未启用
echo ==========================================
echo.
echo 按任意键关闭本窗口（服务将停止）...
pause >nul
