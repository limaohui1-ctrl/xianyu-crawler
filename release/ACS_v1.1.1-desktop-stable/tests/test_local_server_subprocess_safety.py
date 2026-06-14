"""Tests: local server subprocess safety — no shell=True, list args only."""
import sys, os, json, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_no_shell_true_in_source():
    """Code audit: local_server.py must not contain shell=True."""
    import os as _os
    path = _os.path.join(_os.path.dirname(_os.path.dirname(__file__)), "acs", "web", "local_server.py")
    with open(path, encoding="utf-8") as f:
        src = f.read()
    assert "shell=True" not in src, "shell=True found in local_server.py"
    assert "shell = True" not in src
    # Must use list args + shell=False
    assert "subprocess.run" in src


def test_no_os_system_in_source():
    """Code audit: local_server.py must not use os.system()."""
    import os as _os
    path = _os.path.join(_os.path.dirname(_os.path.dirname(__file__)), "acs", "web", "local_server.py")
    with open(path, encoding="utf-8") as f:
        src = f.read()
    assert "os.system" not in src, "os.system() found in local_server.py"
    assert "os.popen" not in src


def test_env_forces_shadow():
    """Verify run-shadow sets ACS_MODE=shadow in environment."""
    import os as _os
    path = _os.path.join(_os.path.dirname(_os.path.dirname(__file__)), "acs", "web", "local_server.py")
    with open(path, encoding="utf-8") as f:
        src = f.read()
    assert '"ACS_MODE": "shadow"' in src, "ACS_MODE=shadow not set in subprocess env"
