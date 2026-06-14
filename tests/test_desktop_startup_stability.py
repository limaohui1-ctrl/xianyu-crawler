"""Tests: desktop startup stability — launcher structure, Chinese paths, error messages."""
import sys, os, re, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_bat_file_contains_chcp():
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "start_acs_desktop.bat")
    with open(path, encoding="utf-8", errors="replace") as f:
        content = f.read()
    assert "chcp 65001" in content, "bat file must set UTF-8 code page for Chinese paths"


def test_bat_file_no_auto_pip_install():
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "start_acs_desktop.bat")
    with open(path, encoding="utf-8", errors="replace") as f:
        content = f.read()
    assert "pip install flask --quiet" not in content, "must not auto-install pip silently"


def test_bat_binds_127_0_0_1():
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "start_acs_desktop.bat")
    with open(path, encoding="utf-8", errors="replace") as f:
        content = f.read()
    assert "127.0.0.1" in content, "must bind 127.0.0.1"
    assert "0.0.0.0" not in content, "must NOT bind 0.0.0.0"


def test_py_launcher_no_auto_install():
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "start_acs_desktop.py")
    with open(path, encoding="utf-8") as f:
        content = f.read()
    assert "pip install flask --quiet" not in content
    assert "requirements.txt" in content, "should reference requirements.txt"


def test_py_launcher_port_occupied_exits():
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "start_acs_desktop.py")
    with open(path, encoding="utf-8") as f:
        content = f.read()
    assert "已被占用" in content
    assert "sys.exit(1)" in content, "occupied port should exit, not ask user"


def test_local_server_no_shell_true():
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "acs", "web", "local_server.py")
    with open(path, encoding="utf-8") as f:
        content = f.read()
    assert "shell=True" not in content
    assert "shell = True" not in content


def test_local_server_binds_localhost():
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "acs", "web", "local_server.py")
    with open(path, encoding="utf-8") as f:
        content = f.read()
    assert "--host" in content
    assert '"127.0.0.1"' in content or "'127.0.0.1'" in content
