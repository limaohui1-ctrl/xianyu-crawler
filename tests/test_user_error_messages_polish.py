"""Tests: user error messages — clear, actionable, no bare Tracebacks."""
import sys, os, re, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_bat_port_occupied_message_clear():
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "start_acs_desktop.bat")
    with open(path, encoding="utf-8", errors="replace") as f:
        src = f.read()
    assert "端口 5020 已被占用" in src
    assert "请先关闭" in src or "关闭占用" in src, "Should tell user to close the occupying program"


def test_bat_deps_missing_shows_requirements():
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "start_acs_desktop.bat")
    with open(path, encoding="utf-8", errors="replace") as f:
        src = f.read()
    assert "requirements.txt" in src, "Should reference requirements.txt"


def test_py_launcher_points_to_requirements():
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "start_acs_desktop.py")
    with open(path, encoding="utf-8") as f:
        src = f.read()
    assert "requirements.txt" in src


def test_local_server_errors_are_user_readable():
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "acs", "web", "local_server.py")
    with open(path, encoding="utf-8") as f:
        src = f.read()
    # Key error messages should exist
    assert "path not allowed" in src
    assert "blocked URLs" in src
    assert "required" in src
    assert "sitemap_url required" in src or "feed_url required" in src


def test_app_js_shows_clear_next_step():
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "acs_ui", "app.js")
    with open(path, encoding="utf-8") as f:
        src = f.read()
    assert "请运行" in src or "start_acs_desktop.bat" in src, "Should tell user to run the launcher"
    assert "网络连接失败" in src or "服务未响应" in src, "Should explain network failure"
