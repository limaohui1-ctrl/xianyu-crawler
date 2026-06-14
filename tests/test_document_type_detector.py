"""Tests for document_type_detector — identify document type from URL/Content-Type/content."""
import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from acs.content.document_type_detector import (
    detect_document_type,
    is_parseable_text_type,
    needs_full_parser,
)


# ── Tests: detect_document_type ──

def test_detect_pdf_by_url_extension():
    """PDF URLs should be detected by extension."""
    assert detect_document_type(url="https://example.com/doc.pdf") == "pdf"
    assert detect_document_type(url="https://example.com/report.PDF") == "pdf"
    assert detect_document_type(url="https://example.com/file.pdf?download=1") == "pdf"


def test_detect_doc_by_url_extension():
    """DOC/DOCX URLs should be detected by extension."""
    assert detect_document_type(url="https://example.com/doc.doc") == "doc"
    assert detect_document_type(url="https://example.com/doc.docx") == "doc"


def test_detect_excel_by_url_extension():
    """Excel URLs should be detected by extension."""
    assert detect_document_type(url="https://example.com/data.xls") == "xls"
    assert detect_document_type(url="https://example.com/data.xlsx") == "xls"


def test_detect_csv_by_url_extension():
    """CSV URLs should be detected by extension."""
    assert detect_document_type(url="https://example.com/data.csv") == "csv"


def test_detect_webpage_by_url():
    """Standard webpage URLs should be detected as webpage."""
    assert detect_document_type(url="https://example.com/page") == "webpage"
    assert detect_document_type(url="https://example.com/article.html") == "webpage"
    assert detect_document_type(url="https://example.com/index.php") == "webpage"


def test_detect_content_type_header_priority():
    """Content-Type header should take priority over URL extension."""
    # URL says .html, but Content-Type says PDF
    result = detect_document_type(
        url="https://example.com/page.html",
        content_type_header="application/pdf",
    )
    assert result == "pdf"


def test_detect_content_type_header_csv():
    """Content-Type header text/csv should return csv."""
    result = detect_document_type(
        url="https://example.com/download",
        content_type_header="text/csv; charset=utf-8",
    )
    assert result == "csv"


def test_detect_content_type_header_doc():
    """Content-Type header for Word document."""
    result = detect_document_type(
        url="https://example.com/download",
        content_type_header="application/msword",
    )
    assert result == "doc"


def test_detect_content_type_header_xls():
    """Content-Type header for Excel."""
    result = detect_document_type(
        url="https://example.com/download",
        content_type_header="application/vnd.ms-excel",
    )
    assert result == "xls"


def test_detect_content_sniff_pdf():
    """Content sniffing should detect PDF magic bytes."""
    result = detect_document_type(
        url="",
        content_type_header="",
        content_sniff="%PDF-1.4 rest of content",
    )
    assert result == "pdf"


def test_detect_unknown():
    """No URL and no content should return unknown."""
    result = detect_document_type(url="", content_type_header="", content_sniff="")
    assert result == "unknown"


def test_detect_ppt_by_extension():
    """PPT/PPTX URLs should be detected."""
    assert detect_document_type(url="https://example.com/slides.ppt") == "ppt"
    assert detect_document_type(url="https://example.com/slides.pptx") == "ppt"


def test_detect_image_by_extension():
    """Image URLs should be detected."""
    assert detect_document_type(url="https://example.com/photo.png") == "image"
    assert detect_document_type(url="https://example.com/photo.jpg") == "image"


# ── Tests: is_parseable_text_type ──

def test_is_parseable_webpage():
    """Webpage should be parseable."""
    assert is_parseable_text_type("webpage") is True


def test_is_parseable_csv():
    """CSV should be parseable."""
    assert is_parseable_text_type("csv") is True


def test_is_parseable_pdf():
    """PDF should NOT be parseable."""
    assert is_parseable_text_type("pdf") is False


def test_is_parseable_doc():
    """DOC should NOT be parseable."""
    assert is_parseable_text_type("doc") is False


# ── Tests: needs_full_parser ──

def test_needs_full_parser_pdf():
    """PDF needs full parser."""
    assert needs_full_parser("pdf") is True


def test_needs_full_parser_doc():
    """DOC needs full parser."""
    assert needs_full_parser("doc") is True


def test_needs_full_parser_webpage():
    """Webpage does NOT need full parser."""
    assert needs_full_parser("webpage") is False


def test_needs_full_parser_csv():
    """CSV does NOT need full parser."""
    assert needs_full_parser("csv") is False
