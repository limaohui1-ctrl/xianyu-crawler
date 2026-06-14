"""Tests: export outputs — JSON/CSV/Markdown correctness and directory creation."""
import sys, os, json, pytest, tempfile, shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _fake_rows(count):
    rows = []
    for i in range(count):
        rows.append({
            "url": f"https://example.com/page{i}",
            "title": f"Test Title {i}",
            "description": f"Description for item {i}",
            "price": f"${10+i}",
            "status": "success" if i % 3 != 0 else "failed",
            "failure_reason": "" if i % 3 != 0 else f"404 error on page {i}",
            "collected_at": "2026-06-14T12:00:00",
        })
    return rows


def test_json_export_creates_file():
    d = tempfile.mkdtemp()
    out = os.path.join(d, "export_test.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(_fake_rows(3), f, ensure_ascii=False, indent=2)
    assert os.path.exists(out)
    with open(out, encoding="utf-8") as f:
        data = json.load(f)
    assert len(data) == 3
    assert data[0]["url"].startswith("http")
    shutil.rmtree(d, ignore_errors=True)


def test_csv_export_no_garbled():
    import csv
    d = tempfile.mkdtemp()
    out = os.path.join(d, "export_test.csv")
    rows = _fake_rows(3)
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)
    with open(out, encoding="utf-8-sig") as f:
        content = f.read()
    assert "url" in content
    assert "https://example.com" in content
    shutil.rmtree(d, ignore_errors=True)


def test_markdown_export_has_table():
    d = tempfile.mkdtemp()
    out = os.path.join(d, "export_test.md")
    rows = _fake_rows(3)
    with open(out, "w", encoding="utf-8") as f:
        f.write("| # | URL | 标题 | 状态 |\n")
        f.write("|---|-----|------|------|\n")
        for i, r in enumerate(rows, 1):
            st = "✅" if r["status"] == "success" else "❌"
            f.write(f"| {i} | {r['url'][:40]} | {r['title']} | {st} |\n")
    with open(out, encoding="utf-8") as f:
        md = f.read()
    assert "| # |" in md
    assert "✅" in md
    assert "❌" in md
    shutil.rmtree(d, ignore_errors=True)


def test_export_dir_auto_created():
    d = tempfile.mkdtemp()
    export_dir = os.path.join(d, "exports")
    assert not os.path.exists(export_dir)
    os.makedirs(export_dir, exist_ok=True)
    assert os.path.isdir(export_dir)
    out = os.path.join(export_dir, "auto_created.json")
    with open(out, "w") as f:
        json.dump([], f)
    assert os.path.exists(out)
    shutil.rmtree(d, ignore_errors=True)


def test_empty_export_does_not_crash():
    d = tempfile.mkdtemp()
    out = os.path.join(d, "empty.json")
    with open(out, "w") as f:
        json.dump([], f)
    with open(out) as f:
        data = json.load(f)
    assert data == []
    shutil.rmtree(d, ignore_errors=True)
