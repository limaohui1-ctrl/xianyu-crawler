@echo off
chcp 65001 >nul
title ACS 资料采集助手 v1.3.1

:: ── Set project root ──
cd /d "%~dp0"

echo.
echo +==========================================+
echo |   ACS 资料采集助手                        |
echo |   v1.3.1-delivery-cleanup                 |
echo |   按主题全网找资料，采集正文，整理导出      |
echo +==========================================+
echo.

:: ── Start ──
python start_acs_desktop.py --no-browser

echo 按任意键关闭本窗口...
pause >nul
