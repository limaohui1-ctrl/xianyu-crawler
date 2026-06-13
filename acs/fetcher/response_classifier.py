"""
Response classifier — determines what kind of content was returned.

Given an HTTP response, classifies it as HTML, JSON, XML, plain text, binary, etc.
This helps the parser engine decide which parser(s) to invoke.

Also detects common error pages, redirect pages, and empty responses.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
import json
import re


class ContentType(str, Enum):
    """High-level content type classification."""
    HTML = "html"
    JSON = "json"
    XML = "xml"
    PLAIN_TEXT = "plain_text"
    BINARY = "binary"
    EMPTY = "empty"
    UNKNOWN = "unknown"


class PageKind(str, Enum):
    """What kind of page is this (sematic classification)."""
    NORMAL = "normal"               # regular content page
    ERROR_PAGE = "error_page"       # server error page (404, 500, etc.)
    REDIRECT_PAGE = "redirect_page" # meta refresh / JS redirect
    LOGIN_PAGE = "login_page"       # login / auth wall
    CAPTCHA_PAGE = "captcha_page"   # captcha / verification
    MAINTENANCE = "maintenance"     # "under maintenance" / coming soon
    EMPTY = "empty"                 # completely empty response
    UNKNOWN = "unknown"


# ── Content type detection patterns ─────────────────────────────

_HTML_SIGNALS = [
    r"<!DOCTYPE\s+html", r"<html", r"<head", r"<body",
    r"<meta\s", r"<div", r"<span", r"<p>", r"<a\s",
]

_JSON_SIGNALS = [
    r'^\s*\[', r'^\s*\{',
]

_XML_SIGNALS = [
    r'<\?xml\s', r'<rss\s', r'<feed\s', r'<urlset\s',
]

# ── Error / special page detection ──────────────────────────────

_LOGIN_INDICATORS = [
    r'login', r'sign\s?in', r'登录', r'登入', r'请登录',
    r'type\s*=\s*["\']password["\']',
    r'name\s*=\s*["\']password["\']',
]

_CAPTCHA_INDICATORS = [
    r'captcha', r'recaptcha', r'hcaptcha', r'验证码',
    r'人机验证', r'机器人验证', r'verify\s+you\s+are',
    r'cf-turnstile', r'g-recaptcha',
]

_ERROR_INDICATORS = [
    r'404\s+(not\s+found|page|页面)', r'500\s+(internal|server|服务)',
    r'502\s+bad\s+gateway', r'503\s+service', r'504\s+gateway',
    r'sorry.*not\s+found', r'page\s+not\s+found',
    r'页面.*不存在', r'页面.*找不到',
]

_REDIRECT_INDICATORS = [
    r'<meta[^>]*http-equiv\s*=\s*["\']refresh["\']',
    r'window\.location\s*=', r'document\.location\s*=',
    r'window\.location\.href\s*=',
]

_MAINTENANCE_INDICATORS = [
    r'under\s+(construction|maintenance)', r'coming\s+soon',
    r'网站.*维护', r'系统.*升级', r'维护中', r'建设中',
]


@dataclass
class ResponseClassification:
    """Classification result for an HTTP response."""

    url: str = ""
    content_type: ContentType = ContentType.UNKNOWN
    page_kind: PageKind = PageKind.NORMAL
    confidence: float = 0.0          # 0.0 – 1.0
    mime_type: str = ""              # from Content-Type header
    http_status: int = 0
    size_bytes: int = 0
    is_empty: bool = False
    is_truncated: bool = False
    detected_encoding: str = ""
    warnings: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_parseable(self) -> bool:
        """Can we extract content from this?"""
        return self.content_type in (
            ContentType.HTML, ContentType.JSON,
            ContentType.XML, ContentType.PLAIN_TEXT,
        ) and self.page_kind in (
            PageKind.NORMAL, PageKind.ERROR_PAGE,
        ) and not self.is_empty

    @property
    def needs_browser(self) -> bool:
        """Does this page likely need JavaScript rendering?"""
        return self.page_kind in (
            PageKind.LOGIN_PAGE, PageKind.CAPTCHA_PAGE,
        ) or self.content_type == ContentType.EMPTY

    @property
    def should_skip(self) -> bool:
        """Should we skip parsing this response entirely?"""
        if self.is_empty:
            return True
        if self.page_kind in (PageKind.CAPTCHA_PAGE, PageKind.MAINTENANCE):
            return True
        if self.content_type == ContentType.BINARY:
            return True
        return False

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "content_type": self.content_type.value,
            "page_kind": self.page_kind.value,
            "confidence": self.confidence,
            "mime_type": self.mime_type,
            "http_status": self.http_status,
            "size_bytes": self.size_bytes,
            "is_empty": self.is_empty,
            "is_truncated": self.is_truncated,
            "detected_encoding": self.detected_encoding,
            "is_parseable": self.is_parseable,
            "needs_browser": self.needs_browser,
            "should_skip": self.should_skip,
            "warnings": self.warnings,
            "details": self.details,
        }


def classify_response(
    url: str,
    body: str,
    http_status: int = 200,
    mime_type: str = "",
    encoding: str = "utf-8",
    max_body_for_detection: int = 20000,
) -> ResponseClassification:
    """Classify an HTTP response body.

    Args:
        url: The request URL
        body: Decoded response body text
        http_status: HTTP status code
        mime_type: Content-Type header value
        encoding: Detected charset

    Returns:
        ResponseClassification with content_type, page_kind, etc.
    """
    classification = ResponseClassification(
        url=url,
        http_status=http_status,
        mime_type=mime_type,
        detected_encoding=encoding,
        size_bytes=len(body.encode(encoding, errors="ignore")),
    )

    # ── Check empty ──
    if not body or not body.strip():
        classification.content_type = ContentType.EMPTY
        classification.page_kind = PageKind.EMPTY
        classification.is_empty = True
        classification.confidence = 1.0
        return classification

    # ── Determine content type ──
    detect_body = body[:max_body_for_detection]
    body_lower = detect_body.lower()

    html_score = sum(1 for pat in _HTML_SIGNALS if re.search(pat, detect_body, re.IGNORECASE))
    json_score = sum(1 for pat in _JSON_SIGNALS if re.search(pat, detect_body.strip()))
    xml_score = sum(1 for pat in _XML_SIGNALS if re.search(pat, detect_body, re.IGNORECASE))

    # Boost based on Content-Type header
    mime_lower = mime_type.lower()
    if "html" in mime_lower:
        html_score += 3
    elif "json" in mime_lower:
        json_score += 3
    elif "xml" in mime_lower or "rss" in mime_lower or "atom" in mime_lower:
        xml_score += 3
    elif "text/plain" in mime_lower:
        classification.content_type = ContentType.PLAIN_TEXT
        classification.confidence = 0.7
        classification.page_kind = PageKind.NORMAL
        return classification

    if html_score >= json_score and html_score >= xml_score and html_score >= 2:
        classification.content_type = ContentType.HTML
        classification.confidence = min(html_score / 8.0, 1.0)
    elif json_score >= html_score and json_score >= 1:
        classification.content_type = ContentType.JSON
        classification.confidence = min(json_score / 3.0, 1.0)
    elif xml_score >= 1:
        classification.content_type = ContentType.XML
        classification.confidence = min(xml_score / 3.0, 1.0)
    else:
        classification.content_type = ContentType.PLAIN_TEXT
        classification.confidence = 0.3

    # ── Detect page kind (HTML only) ──
    if classification.content_type == ContentType.HTML:
        classification.page_kind = _detect_html_page_kind(body_lower[:10000])
    elif classification.content_type == ContentType.JSON:
        classification.page_kind = PageKind.NORMAL
    else:
        classification.page_kind = PageKind.NORMAL

    # ── Warnings ──
    if classification.content_type == ContentType.PLAIN_TEXT and classification.confidence < 0.5:
        classification.warnings.append("无法确定内容类型，按纯文本处理")

    if http_status >= 400:
        classification.warnings.append(f"HTTP {http_status}")

    return classification


def _detect_html_page_kind(html_lower: str) -> PageKind:
    """Classify the semantic kind of an HTML page."""

    # Check captcha first (highest priority)
    for pat in _CAPTCHA_INDICATORS:
        if re.search(pat, html_lower):
            return PageKind.CAPTCHA_PAGE

    # Check login
    for pat in _LOGIN_INDICATORS:
        if re.search(pat, html_lower):
            return PageKind.LOGIN_PAGE

    # Check maintenance
    for pat in _MAINTENANCE_INDICATORS:
        if re.search(pat, html_lower):
            return PageKind.MAINTENANCE

    # Check error page
    for pat in _ERROR_INDICATORS:
        if re.search(pat, html_lower):
            return PageKind.ERROR_PAGE

    # Check redirect
    for pat in _REDIRECT_INDICATORS:
        if re.search(pat, html_lower):
            return PageKind.REDIRECT_PAGE

    return PageKind.NORMAL
