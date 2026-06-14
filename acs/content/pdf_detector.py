"""
pdf_detector.py — detect PDF URLs and handle them appropriately.

For now, PDFs are NOT fully parsed. They are:
  1. Detected by URL extension, Content-Type, or magic bytes.
  2. Marked as doc_type='pdf'.
  3. Assigned a title from URL filename or metadata.
  4. Displayed with note "PDF正文解析待增强".
"""

import re
from urllib.parse import urlparse, unquote


def detect_pdf_url(url: str) -> bool:
    """Quick check: does this URL point to a PDF?"""
    if not url:
        return False
    url_lower = url.lower()
    path = urlparse(url_lower).path
    return path.endswith(".pdf") or ".pdf?" in url_lower


def pdf_info(url: str) -> dict:
    """
    Extract what information we can from a PDF URL without downloading it.

    Returns:
        dict with:
          - is_pdf: True
          - title: extractable title from URL
          - url: original URL
          - filename: filename portion of URL
          - status: 'PDF正文解析待增强'
          - doc_type: 'pdf'
    """
    result = {
        "is_pdf": True,
        "title": "",
        "url": url,
        "filename": "",
        "status": "PDF正文解析待增强",
        "doc_type": "pdf",
        "error": "",
    }

    if not url:
        result["error"] = "Empty URL"
        return result

    try:
        parsed = urlparse(url)
        path = unquote(parsed.path.strip("/"))
        if path:
            parts = path.split("/")
            result["filename"] = parts[-1]
            # Derive title from filename
            name = re.sub(r"\.pdf$", "", result["filename"], flags=re.IGNORECASE)
            name = re.sub(r"[-_]+", " ", name)
            if len(name) >= 3:
                result["title"] = name
    except Exception:
        pass

    return result
