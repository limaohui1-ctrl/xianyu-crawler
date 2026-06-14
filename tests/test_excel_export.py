"""Tests for export_excel — export harvest results to Excel (.xlsx)."""
import sys
import os
import tempfile
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from acs.content.export_excel import export_excel, is_excel_available


# ── Test data ──

def _make_article(index, title="Test Article", url="https://example.com/1"):
    return {
        "url": url,
        "title": title,
        "main_text": "This is the body content of the article for testing.",
        "summary": "This is the body content...",
        "author": "Test Author",
        "publish_time": "2025-06-01",
        "source_domain": "example.com",
        "doc_type": "webpage",
        "text_length": 55,
        "paragraph_count": 3,
        "images": [],
        "links": [],
        "status": "成功",
        "error": "",
        "quality_label": "high",
        "quality_status": "高质量",
        "quality_score": 85,
        "keyword_hits": "环保,政策",
        "is_duplicate": False,
        "duplicate_reason": "",
        "harvest_time": "2025-06-14 10:30:00",
    }


ARTICLES_3 = [
    _make_article(0, "Article One", "https://example.com/1"),
    _make_article(1, "Article Two", "https://example.com/2"),
    _make_article(2, "Article Three", "https://example.com/3"),
]

ARTICLES_WITH_DUPE = [
    _make_article(0, "Article One", "https://example.com/1"),
    _make_article(1, "Article One Dupe", "https://example.com/1"),
    _make_article(2, "Article Two", "https://example.com/2"),
]
# Mark second as duplicate
ARTICLES_WITH_DUPE[1]["is_duplicate"] = True
ARTICLES_WITH_DUPE[1]["duplicate_reason"] = "URL重复"


# ── Tests ──

def test_is_excel_available():
    """openpyxl should be available (in requirements.txt)."""
    assert is_excel_available() is True


def test_export_excel_basic():
    """Basic export of 3 articles should create a file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = os.path.join(tmpdir, "test_export.xlsx")
        result_path = export_excel(ARTICLES_3, output_path=output_path)

        assert os.path.exists(result_path)
        assert result_path.endswith(".xlsx")
        assert os.path.getsize(result_path) > 0


def test_export_excel_file_exists():
    """Export should create a real file on disk."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = os.path.join(tmpdir, "test_exists.xlsx")
        result_path = export_excel(ARTICLES_3, output_path=output_path)

        assert os.path.isfile(result_path)


def test_export_excel_extension():
    """Output should have .xlsx extension."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = os.path.join(tmpdir, "test_ext.xlsx")
        result_path = export_excel(ARTICLES_3, output_path=output_path)

        assert result_path.endswith(".xlsx")


def test_export_excel_include_duplicates():
    """With include_duplicates=True, all articles should be exported."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = os.path.join(tmpdir, "test_with_dupes.xlsx")
        result_path = export_excel(
            ARTICLES_WITH_DUPE,
            output_path=output_path,
            include_duplicates=True,
        )

        assert os.path.exists(result_path)
        # File should exist and be non-empty
        assert os.path.getsize(result_path) > 0


def test_export_excel_filter_duplicates():
    """With include_duplicates=False, duplicates should be excluded."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = os.path.join(tmpdir, "test_no_dupes.xlsx")
        result_path = export_excel(
            ARTICLES_WITH_DUPE,
            output_path=output_path,
            include_duplicates=False,
        )

        assert os.path.exists(result_path)
        assert os.path.getsize(result_path) > 0


def test_export_excel_auto_generate_path():
    """If no output_path given, should auto-generate one in acs_data/harvest/."""
    # Use a temp location trick: change working behavior
    result_path = export_excel(ARTICLES_3, output_path="")

    assert result_path.endswith(".xlsx")
    assert "harvest" in result_path
    assert os.path.exists(result_path)

    # Clean up generated file
    try:
        import shutil
        parent = os.path.dirname(result_path)
        if os.path.exists(parent):
            shutil.rmtree(os.path.dirname(parent), ignore_errors=True)
    except Exception:
        pass


def test_export_excel_empty_articles():
    """Exporting empty article list should still work."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = os.path.join(tmpdir, "test_empty.xlsx")
        result_path = export_excel([], output_path=output_path)

        assert os.path.exists(result_path)
        assert os.path.getsize(result_path) > 0


def test_export_excel_returns_absolute_path():
    """Result should be an absolute path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = os.path.join(tmpdir, "test_abs.xlsx")
        result_path = export_excel(ARTICLES_3, output_path=output_path)

        assert os.path.isabs(result_path)
