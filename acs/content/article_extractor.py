"""
article_extractor.py — full content extraction pipeline for one URL.

Orchestrates:
  1. html_cleaner — strip boilerplate
  2. metadata_extractor — title, author, date, domain
  3. main_text_extractor — body paragraphs, summary
  4. document_type_detector — webpage/pdf/doc/...
  5. pdf_detector — PDF handling

Output: a ContentRecord dict ready for quality scoring and export.
"""

from typing import Optional

from .html_cleaner import clean_html
from .metadata_extractor import extract_metadata
from .main_text_extractor import extract_main_text
from .document_type_detector import detect_document_type, is_parseable_text_type
from .pdf_detector import detect_pdf_url, pdf_info


def extract_article(html: str = "",
                    url: str = "",
                    content_type_header: str = "",
                    http_status: int = 200,
                    ) -> dict:
    """
    Full content extraction pipeline.

    Args:
        html: Raw HTML (or empty for non-HTML resources).
        url: Source URL.
        content_type_header: HTTP Content-Type header.
        http_status: HTTP status code.

    Returns:
        ContentRecord dict:
          url, title, main_text, summary, author, publish_time,
          source_domain, doc_type, text_length, paragraph_count,
          images, links, status, error, quality_label
    """
    result = {
        "url": url,
        "title": "",
        "main_text": "",
        "summary": "",
        "author": "",
        "publish_time": "",
        "source_domain": "",
        "doc_type": "unknown",
        "text_length": 0,
        "paragraph_count": 0,
        "images": [],
        "links": [],
        "status": "pending",
        "error": "",
        "quality_label": "low",
    }

    # ── Step 0: Check HTTP status ──
    if http_status >= 400:
        result["status"] = "失败"
        result["error"] = f"HTTP {http_status}"
        return result

    # ── Step 1: Detect document type ──
    doc_type = detect_document_type(url, content_type_header,
                                    html[:1024] if html else "")
    result["doc_type"] = doc_type

    # ── Step 2: Handle PDF ──
    if doc_type == "pdf" or detect_pdf_url(url):
        pdf = pdf_info(url)
        result.update({
            "doc_type": "pdf",
            "title": pdf["title"] or result["title"],
            "status": "PDF正文解析待增强",
            "error": "PDF full-text parsing not yet implemented",
        })
        result["source_domain"] = pdf.get("url", url)
        return result

    # ── Step 3: Handle non-text documents ──
    if doc_type in ("doc", "docx", "xls", "xlsx", "ppt", "pptx"):
        # Extract metadata from URL if possible
        meta = extract_metadata(html or "", url, content_type_hint=doc_type)
        result["title"] = meta["title"] or result["title"]
        result["source_domain"] = meta["source_domain"]
        result["status"] = "文档类型已识别，正文解析未实现"
        result["error"] = f"{doc_type.upper()} document — full parsing not yet available"
        if not result["title"]:
            result["error"] = f"{doc_type.upper()} document — no title extracted"
        return result

    # ── Step 4: Handle webpages ──
    if not html or not html.strip():
        result["status"] = "失败"
        result["error"] = "No HTML content to extract"
        return result

    # Step 4a: Clean HTML
    clean = clean_html(html)
    if clean["error"]:
        result["status"] = "失败"
        result["error"] = clean["error"]
        return result

    # Step 4b: Extract metadata
    meta = extract_metadata(clean["cleaned_html"], url)
    result["title"] = meta["title"] or result["title"]
    result["author"] = meta.get("author", "")
    result["publish_time"] = meta.get("publish_time", "")
    result["source_domain"] = meta.get("source_domain", "")

    # Step 4c: Extract main text
    text = extract_main_text(clean["cleaned_html"])
    result["main_text"] = text.get("main_text", "")
    result["summary"] = text.get("summary", "")
    result["paragraph_count"] = text.get("paragraph_count", 0)
    result["text_length"] = text.get("text_length", 0)
    if text.get("error"):
        result["error"] = text["error"]

    # Step 4d: Determine status
    if result["main_text"] and len(result["main_text"].strip()) >= 50:
        result["status"] = "成功"
    elif result["main_text"] and len(result["main_text"].strip()) > 0:
        result["status"] = "正文较短"
    else:
        result["status"] = "失败"
        if not result["error"]:
            result["error"] = "Failed to extract meaningful text"

    # Step 4e: Initial quality label
    if result["text_length"] >= 500 and result["title"] and result["paragraph_count"] >= 3:
        result["quality_label"] = "high"
    elif result["text_length"] >= 100:
        result["quality_label"] = "medium"
    else:
        result["quality_label"] = "low"

    return result
