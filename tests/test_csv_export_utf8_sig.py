"""Tests: CSV export uses utf-8-sig encoding for Excel compatibility."""
import sys, os, csv, json, pytest, tempfile, shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_local_server_csv_export_uses_utf8_sig():
    """Verify local_server.py CSV export code uses utf-8-sig."""
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "acs", "web", "local_server.py")
    with open(path, encoding="utf-8") as f:
        src = f.read()
    assert "utf-8-sig" in src, "CSV export must use utf-8-sig encoding"


def test_csv_with_bom_opened_in_excel_style():
    """Verify CSV with BOM is valid and Excel-compatible."""
    d = tempfile.mkdtemp()
    out = os.path.join(d, "test_bom.csv")
    rows = [
        {"url": "https://example.com/1", "标题": "测试资料", "状态": "成功"},
        {"url": "https://example.com/2", "标题": "第二份资料", "状态": "成功"},
    ]
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["url", "标题", "状态"])
        w.writeheader()
        w.writerows(rows)

    # Read back as utf-8-sig
    with open(out, "r", encoding="utf-8-sig") as f:
        content = f.read()
    assert "url" in content
    assert "标题" in content
    assert "测试资料" in content
    # BOM should be stripped on read
    assert not content.startswith("\ufeff")
    shutil.rmtree(d, ignore_errors=True)


def test_csv_no_bom_in_plain_utf8():
    """Contrast: plain utf-8 CSV has no BOM."""
    d = tempfile.mkdtemp()
    out = os.path.join(d, "plain.csv")
    with open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["url", "title"])
        w.writerow(["https://x.com", "test"])
    with open(out, "rb") as f:
        first_bytes = f.read(3)
    assert first_bytes != b"\xef\xbb\xbf", "Plain UTF-8 should not have BOM"
    shutil.rmtree(d, ignore_errors=True)
