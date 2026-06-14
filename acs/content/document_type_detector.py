"""
document_type_detector.py — identify document type from URL, Content-Type, and content.

Categories:
  webpage  — HTML page
  pdf      — PDF document
  doc      — Word document (.doc / .docx)
  xls      — Excel spreadsheet (.xls / .xlsx)
  csv      — CSV file
  ppt      — PowerPoint
  image    — Image file
  unknown  — Could not determine
"""

import re
from typing import Optional
from urllib.parse import urlparse


# Extension → type mapping
EXTENSION_TO_TYPE = {
    ".pdf":   "pdf",
    ".doc":   "doc",
    ".docx":  "doc",
    ".xls":   "xls",
    ".xlsx":  "xls",
    ".csv":   "csv",
    ".ppt":   "ppt",
    ".pptx":  "ppt",
    ".png":   "image",
    ".jpg":   "image",
    ".jpeg":  "image",
    ".gif":   "image",
    ".svg":   "image",
    ".webp":  "image",
    ".htm":   "webpage",
    ".html":  "webpage",
    ".asp":   "webpage",
    ".aspx":  "webpage",
    ".php":   "webpage",
    ".jsp":   "webpage",
}

# MIME type → type mapping
MIME_TO_TYPE = {
    "application/pdf": "pdf",
    "application/msword": "doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "doc",
    "application/vnd.ms-excel": "xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xls",
    "text/csv": "csv",
    "application/vnd.ms-powerpoint": "ppt",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "ppt",
    "text/html": "webpage",
    "application/xhtml+xml": "webpage",
    "image/png": "image",
    "image/jpeg": "image",
    "image/gif": "image",
    "image/svg+xml": "image",
    "image/webp": "image",
}


def detect_document_type(url: str = "",
                         content_type_header: str = "",
                         content_sniff: str = "") -> str:
    """
    Determine the document type of a URL/resource.

    Priority: MIME type > URL extension > content sniff

    Args:
        url: The URL of the resource.
        content_type_header: HTTP Content-Type header value.
        content_sniff: First 1024 bytes of content for magic-byte detection.

    Returns:
        One of: webpage, pdf, doc, xls, csv, ppt, image, unknown
    """
    # 1. MIME type from Content-Type header (most reliable)
    if content_type_header:
        mime_main = content_type_header.split(";")[0].strip().lower()
        if mime_main in MIME_TO_TYPE:
            return MIME_TO_TYPE[mime_main]

    # 2. URL extension
    if url:
        url_lower = url.lower()
        # Strip query params for extension detection
        path = urlparse(url_lower).path
        for ext, dtype in EXTENSION_TO_TYPE.items():
            if path.endswith(ext) or f"{ext}?" in url_lower:
                return dtype

    # 3. Content sniff (magic bytes)
    if content_sniff:
        sniff = content_sniff[:16].lower()
        if sniff.startswith("%pdf"):
            return "pdf"
        if sniff.startswith("\xd0\xcf\x11\xe0"):  # OLE2 (doc/xls/ppt)
            return "doc"  # conservative — could be xls/ppt
        if sniff.startswith("pk\x03\x04"):
            # ZIP-based Office Open XML — check internal filenames
            if b"word/" in content_sniff.encode("latin-1", errors="ignore")[:1024]:
                return "doc"
            if b"xl/" in content_sniff.encode("latin-1", errors="ignore")[:1024]:
                return "xls"
            if b"ppt/" in content_sniff.encode("latin-1", errors="ignore")[:1024]:
                return "ppt"
            return "xls"  # generic ZIP → assume Excel (most common for data)

    # 4. Heuristic: if URL has no recognizable extension, it's a webpage
    if url and urlparse(url).path:
        return "webpage"

    return "unknown"


def is_parseable_text_type(doc_type: str) -> bool:
    """Return True if this document type can have its full text extracted."""
    return doc_type in ("webpage", "csv")


def needs_full_parser(doc_type: str) -> bool:
    """Return True if this document type needs external tools for full parsing."""
    return doc_type in ("pdf", "doc", "docx", "xls", "ppt")
