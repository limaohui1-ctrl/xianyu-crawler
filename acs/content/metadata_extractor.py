"""
metadata_extractor.py — extract title, author, publish_time, source_domain
from HTML and HTTP response.

Uses:
  - <title> tag
  - <meta> tags (author, description, publish date)
  - OpenGraph / Twitter Card meta tags
  - JSON-LD (schema.org Article / WebPage)
  - HTTP headers
"""

import re
import json
from datetime import datetime
from typing import Optional, Dict, Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag


def _safe_meta(soup, attrs: dict) -> Optional[str]:
    """Find a <meta> tag matching attrs and return its content."""
    tag = soup.find("meta", attrs=attrs)
    if tag:
        return (tag.get("content") or "").strip()
    return None


def _parse_iso_date(text: str) -> str:
    """Try to parse an ISO-ish date string, return YYYY-MM-DD or original."""
    if not text:
        return ""
    patterns = [
        r"(\d{4}-\d{2}-\d{2})",
        r"(\d{4}/\d{2}/\d{2})",
        r"(\d{4}\.\d{2}\.\d{2})",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return m.group(1).replace("/", "-").replace(".", "-")
    return text[:50]


def extract_metadata(html: str, url: str = "",
                     content_type_hint: str = "") -> dict:
    """
    Extract metadata from an HTML page.

    Args:
        html: Raw or cleaned HTML.
        url: Source URL.
        content_type_hint: e.g. 'pdf', 'doc' — used when HTML is absent.

    Returns:
        dict with: title, author, publish_time, source_domain, description, language
    """
    result = {
        "title": "",
        "author": "",
        "publish_time": "",
        "source_domain": "",
        "description": "",
        "language": "",
        "error": "",
    }

    # Domain
    if url:
        try:
            result["source_domain"] = urlparse(url).netloc.lower()
        except Exception:
            pass

    # For non-HTML content types, bail early with a clear message
    if content_type_hint in ("pdf", "doc", "docx", "xls", "xlsx", "csv", "ppt", "pptx"):
        # Try to extract a title from the URL path
        if url:
            path_parts = urlparse(url).path.strip("/").split("/")
            if path_parts:
                filename = path_parts[-1]
                # Remove extension
                name = re.sub(r"\.[^.]{2,5}$", "", filename)
                # Replace dashes/underscores with spaces
                name = re.sub(r"[-_]+", " ", name)
                if len(name) >= 3:
                    result["title"] = name
        return result

    if not html or not html.strip():
        result["error"] = "No HTML to extract metadata from"
        return result

    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception as e:
        result["error"] = f"HTML parse failed: {e}"
        return result

    # ── Title ──
    # Priority: og:title > twitter:title > <title> > h1
    og_title = _safe_meta(soup, {"property": "og:title"})
    twitter_title = _safe_meta(soup, {"name": "twitter:title"})
    html_title = soup.title.get_text(strip=True) if soup.title else ""
    h1 = soup.find("h1")
    h1_text = h1.get_text(strip=True) if h1 else ""

    for candidate in [og_title, twitter_title, html_title, h1_text]:
        if candidate and candidate.strip():
            result["title"] = candidate.strip()[:500]
            break

    # ── Author ──
    # Priority: article:author > author meta > og:article:author > JSON-LD
    for attrs in [
        {"name": "author"},
        {"name": "article:author"},
        {"property": "article:author"},
        {"property": "og:article:author"},
        {"name": "twitter:creator"},
    ]:
        val = _safe_meta(soup, attrs)
        if val:
            result["author"] = val[:200]
            break

    # ── Publish time ──
    for attrs in [
        {"name": "article:published_time"},
        {"property": "article:published_time"},
        {"name": "pubdate"},
        {"name": "publish_date"},
        {"name": "date"},
        {"property": "og:article:published_time"},
    ]:
        val = _safe_meta(soup, attrs)
        if val:
            parsed = _parse_iso_date(val)
            if parsed:
                result["publish_time"] = parsed
                break

    # Try <time> element
    if not result["publish_time"]:
        time_el = soup.find("time")
        if time_el:
            dt = time_el.get("datetime") or time_el.get_text(strip=True)
            if dt:
                result["publish_time"] = _parse_iso_date(dt)

    # ── Description ──
    for attrs in [
        {"name": "description"},
        {"property": "og:description"},
        {"name": "og:description"},
    ]:
        val = _safe_meta(soup, attrs)
        if val:
            result["description"] = val[:500]
            break

    # ── Language ──
    html_tag = soup.find("html")
    if html_tag:
        result["language"] = (html_tag.get("lang") or html_tag.get("xml:lang") or "")[:10]
    if not result["language"]:
        content_lang = _safe_meta(soup, {"http-equiv": "content-language"})
        if content_lang:
            result["language"] = content_lang[:10]

    return result
