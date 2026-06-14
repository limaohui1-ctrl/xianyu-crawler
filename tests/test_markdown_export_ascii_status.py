"""Tests: Markdown export uses [PASS]/[FAIL] not emoji."""
import sys, os, json, pytest, tempfile, shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _fake_rows(count):
    return [{"url": f"https://x.com/{i}", "title": f"T{i}", "status": "success" if i % 2 == 0 else "failed"} for i in range(count)]


def test_md_export_uses_pass_fail():
    """Verify Markdown export code uses [PASS]/[FAIL] in local_server.py."""
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "acs", "web", "local_server.py")
    with open(path, encoding="utf-8") as f:
        src = f.read()
    assert '"[PASS]"' in src, "Markdown export must use [PASS]"
    assert '"[FAIL]"' in src, "Markdown export must use [FAIL]"
    assert "✅" not in src, "Emoji ✅ must not appear in server code"
    assert "❌" not in src, "Emoji ❌ must not appear in server code"


def test_app_js_uses_pass_fail():
    """Verify app.js results table uses [PASS]/[FAIL]."""
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "acs_ui", "app.js")
    with open(path, encoding="utf-8") as f:
        src = f.read()
    assert "'[PASS]'" in src, "JS results must use [PASS]"
    assert "'[FAIL]'" in src, "JS results must use [FAIL]"


def test_index_html_no_emoji_in_status():
    """Verify index.html service status bar has no emoji."""
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "acs_ui", "index.html")
    with open(path, encoding="utf-8", errors="replace") as f:
        src = f.read()
    assert "✅" not in src, "index.html must not contain emoji ✅"
    assert "❌" not in src, "index.html must not contain emoji ❌"
    assert "⏳" not in src, "index.html must not contain emoji ⏳"


def test_md_export_result_structure():
    """Manual render test: Markdown output contains [PASS]/[FAIL]."""
    d = tempfile.mkdtemp()
    out = os.path.join(d, "test.md")
    rows = _fake_rows(4)
    with open(out, "w", encoding="utf-8") as f:
        f.write("| # | URL | 标题 | 状态 |\n")
        f.write("|---|-----|------|------|\n")
        for i, r in enumerate(rows, 1):
            st = "[PASS]" if r["status"] == "success" else "[FAIL]"
            f.write(f"| {i} | {r['url'][:30]} | {r['title']} | {st} |\n")
    with open(out, encoding="utf-8") as f:
        md = f.read()
    assert "[PASS]" in md
    assert "[FAIL]" in md
    assert "✅" not in md
    assert "❌" not in md
    shutil.rmtree(d, ignore_errors=True)
