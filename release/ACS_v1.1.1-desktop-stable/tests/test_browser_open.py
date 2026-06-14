"""Tests for browser_open."""
import sys, os, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.web.browser_open import open_browser


def test_open_browser_url(monkeypatch):
    calls = []
    def fake_open(url):
        calls.append(url)
    monkeypatch.setattr("webbrowser.open", fake_open)
    open_browser("https://example.com")
    assert len(calls) == 1
    assert calls[0] == "https://example.com"


def test_open_browser_local_file(monkeypatch):
    calls = []
    def fake_open(url):
        calls.append(url)
    monkeypatch.setattr("webbrowser.open", fake_open)
    import tempfile, shutil
    d = tempfile.mkdtemp()
    p = os.path.join(d, "test.html")
    with open(p, "w") as f:
        f.write("<html></html>")
    open_browser(p)
    assert len(calls) == 1
    assert "test.html" in calls[0]
    shutil.rmtree(d, ignore_errors=True)


def test_open_browser_file_not_found():
    with pytest.raises(FileNotFoundError):
        open_browser("nonexistent_file_12345.html")


def test_open_browser_empty():
    open_browser("")  # should not crash
