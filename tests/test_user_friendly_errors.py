"""Tests: user-friendly errors — clear Chinese messages, no bare Tracebacks in UI."""
import sys, os, re, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_local_server_has_user_readable_errors():
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "acs", "web", "local_server.py")
    with open(path, encoding="utf-8") as f:
        src = f.read()

    # Must have Chinese/clear error messages for common failures
    assert "端口" in src or "port" in src.lower(), "should mention port in errors"
    assert "path not allowed" in src, "should have path safety error in English"
    assert "blocked URLs" in src, "should reject blocked URLs clearly"
    assert "required" in src, "should say when params are required"


def test_bat_has_clear_error_messages():
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "start_acs_desktop.bat")
    with open(path, encoding="utf-8", errors="replace") as f:
        src = f.read()
    assert "已被占用" in src, "should say port is occupied in Chinese"
    assert "未安装" in src, "should say dependencies are missing in Chinese"


def test_py_launcher_has_clear_error_messages():
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "start_acs_desktop.py")
    with open(path, encoding="utf-8") as f:
        src = f.read()
    assert "已被占用" in src, "should say port occupied in Chinese"
    assert "缺少依赖" in src, "should say missing deps in Chinese"
    assert "requirements.txt" in src


def test_app_js_has_fallback_messages():
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "acs_ui", "app.js")
    with open(path, encoding="utf-8") as f:
        src = f.read()
    assert "网络连接失败" in src or "服务未响应" in src, "should show network error in Chinese"
    assert "本地服务未连接" in src or "请运行" in src, "should guide user to start server"
