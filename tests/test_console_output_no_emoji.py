"""Tests: console output has no emoji in launchers, uses ASCII-only status labels."""
import sys, os, re, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


EMOJI = list("✅❌⚠️⏳🧠📊📋📂📥📄📝🔍🔄▶☑✕🗓⚙ℹ🔒")


def test_bat_no_emoji():
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "start_acs_desktop.bat")
    with open(path, encoding="utf-8", errors="replace") as f:
        src = f.read()
    for ch in EMOJI:
        assert ch not in src, f"bat must not contain emoji: {ch!r}"
    assert "╔" not in src, "bat must not contain box-drawing chars"
    assert "║" not in src
    assert "╚" not in src
    assert "╗" not in src
    assert "╝" not in src
    assert "═" not in src


def test_py_launcher_no_emoji():
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "start_acs_desktop.py")
    with open(path, encoding="utf-8") as f:
        src = f.read()
    for ch in EMOJI:
        assert ch not in src, f"py launcher must not contain emoji: {ch!r}"
    assert "╔" not in src
    assert "║" not in src
    assert "╚" not in src
    assert "╝" not in src
    assert "═" not in src


def test_bat_uses_ascii_labels():
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "start_acs_desktop.bat")
    with open(path, encoding="utf-8", errors="replace") as f:
        src = f.read()
    assert "[ERROR]" in src or "[ERROR] " in src
    assert "[OK]" in src or "[OK] " in src


def test_py_launcher_uses_ascii_labels():
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "start_acs_desktop.py")
    with open(path, encoding="utf-8") as f:
        src = f.read()
    assert "[ERROR]" in src
    assert "[OK]" in src
    assert "[WARN]" in src
