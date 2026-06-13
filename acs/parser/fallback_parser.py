"""
Fallback parser — the last-resort parser that always succeeds.

When all other parsers fail or can't handle the content, this parser
extracts whatever it can using regex and heuristics.  It guarantees
that a ParseResult is always returned, even if mostly empty.
"""

from typing import List, Optional
from urllib.parse import urlparse, urljoin
import re

from acs.core.result_model import ParseResult, PageImage, PageLink
from acs.fetcher.response_classifier import ContentType
from acs.parser.parser_engine import BaseParser


MAX_TEXT_LENGTH = 20000
MAX_IMAGES = 80
MAX_LINKS = 200


def _compact_text(text, limit=MAX_TEXT_LENGTH):
    if not text:
        return ""
    text = re.sub(r"[\r\t]+", " ", str(text))
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)
    return text.strip()[:limit]


class FallbackParser(BaseParser):
    """Last-resort parser — always succeeds, uses regex heuristics."""

    name = "fallback"

    def can_handle(self, content_type: ContentType, body: str) -> bool:
        """Always returns True — this is the safety net."""
        return True

    def parse(self, url: str, body: str, **kwargs) -> ParseResult:
        result = ParseResult(url=url, parser_used="fallback")

        if not body or not body.strip():
            result.error = "Empty body"
            result.error_category = "content_empty"
            result.build()
            return result

        body_stripped = body.strip()

        # ── Title ──
        result.title = self._extract_title(body_stripped)

        # ── Author ──
        result.author = self._extract_author(body_stripped)

        # ── Published time ──
        result.published_time = self._extract_time(body_stripped)

        # ── Price ──
        result.price = self._extract_price(body_stripped)

        # ── Body ──
        result.body = self._extract_body(body_stripped)

        # ── Images ──
        result.images = self._extract_images(body_stripped, url)

        # ── Links ──
        result.links = self._extract_links(body_stripped, url)

        result.build()
        return result

    # ── Private extractors ──────────────────────────────────────

    def _extract_title(self, text: str) -> str:
        """Try to find a title: <title>, og:title, or first meaningful line."""
        # <title> tag
        m = re.search(r'<title[^>]*>(.+?)</title>', text, re.IGNORECASE | re.DOTALL)
        if m:
            raw = m.group(1).strip()
            # Decode HTML entities
            import html
            raw = html.unescape(raw)
            # Strip HTML tags in title
            raw = re.sub(r'<[^>]+>', '', raw)
            if raw:
                return _compact_text(raw, 500)

        # og:title
        m = re.search(r'<meta[^>]*property=["\']og:title["\'][^>]*content=["\']([^"\']+)["\']', text, re.IGNORECASE)
        if not m:
            m = re.search(r'<meta[^>]*content=["\']([^"\']+)["\'][^>]*property=["\']og:title["\']', text, re.IGNORECASE)
        if m:
            return _compact_text(m.group(1), 500)

        # h1
        m = re.search(r'<h1[^>]*>(.+?)</h1>', text, re.IGNORECASE | re.DOTALL)
        if m:
            raw = re.sub(r'<[^>]+>', '', m.group(1)).strip()
            if raw:
                return _compact_text(raw, 500)

        # First non-empty, non-tag line that looks like a title
        lines = text.split("\n")
        for line in lines[:30]:
            line = line.strip()
            # Skip lines that look like tags or boilerplate
            if line.startswith("<") or len(line) < 10:
                continue
            if re.search(r'[\u4e00-\u9fff]', line):  # Contains Chinese
                return _compact_text(line, 500)
            # English title-like
            if re.match(r'^[A-Z][\w\s\-:]{10,}', line):
                return _compact_text(line, 500)

        return ""

    def _extract_author(self, text: str) -> str:
        """Try to find an author: meta tag or byline pattern."""
        # meta author
        m = re.search(r'<meta[^>]*name=["\']author["\'][^>]*content=["\']([^"\']+)["\']', text, re.IGNORECASE)
        if not m:
            m = re.search(r'<meta[^>]*content=["\']([^"\']+)["\'][^>]*name=["\']author["\']', text, re.IGNORECASE)
        if m:
            return _compact_text(m.group(1), 200)

        # byline patterns
        m = re.search(r'(?:作者|发布者|作者：|发布者：|By|by)\s*[:：]?\s*([^\n<]{2,40})', text)
        if m:
            return _compact_text(m.group(1), 200)

        return ""

    def _extract_time(self, text: str) -> str:
        """Try to find a published time."""
        patterns = [
            r'<meta[^>]*property=["\']article:published_time["\'][^>]*content=["\']([^"\']+)["\']',
            r'<meta[^>]*property=["\']article:modified_time["\'][^>]*content=["\']([^"\']+)["\']',
            r'<meta[^>]*name=["\']pubdate["\'][^>]*content=["\']([^"\']+)["\']',
            r'<time[^>]*datetime=["\']([^"\']+)["\']',
            r'(\d{4}[-/]\d{1,2}[-/]\d{1,2}[T ]\d{1,2}:\d{2})',
            r'(\d{4}年\d{1,2}月\d{1,2}日)',
            r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})',
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                return _compact_text(m.group(1), 100)

        return ""

    def _extract_price(self, text: str) -> str:
        """Try to find a price: currency symbol + number pattern."""
        patterns = [
            r'(?:¥|￥|价格|售价|price)[:\s]*\s*([\d,]+\.?\d*)',
            r'([¥￥$€£]\s*[\d,]+\.?\d*)',
            r'([\d,]+\.?\d*\s*[元块])',
            r'<meta[^>]*property=["\']product:price:amount["\'][^>]*content=["\']([^"\']+)["\']',
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                return _compact_text(m.group(0), 60)

        return ""

    def _extract_body(self, text: str) -> str:
        """Extract body text: strip tags, keep paragraphs."""
        # Remove script/style blocks
        clean = re.sub(r'<(script|style|noscript|iframe|svg)[^>]*>.*?</\1>', '', text,
                       flags=re.DOTALL | re.IGNORECASE)

        # Try to find main content area
        for tag in ('article', 'main', 'div[class*="content"]', 'div[class*="article"]',
                     'div[class*="post"]', 'div[class*="body"]', 'div[id*="content"]'):
            m = re.search(
                rf'<{tag}[^>]*>(.*?)</{re.escape(tag.split("[")[0])}>',
                clean, re.DOTALL | re.IGNORECASE
            )
            if m:
                inner = m.group(1)
                # Strip remaining tags
                inner = re.sub(r'<[^>]+>', '\n', inner)
                inner = re.sub(r'\n\s*\n', '\n\n', inner)
                if len(inner.strip()) > 100:
                    return _compact_text(inner)

        # Strip all tags
        body = re.sub(r'<[^>]+>', '\n', clean)
        body = re.sub(r'\n\s*\n', '\n\n', body)
        # Remove excessive blank lines
        body = re.sub(r'\n{3,}', '\n\n', body)
        return _compact_text(body.strip())

    def _extract_images(self, text: str, base_url: str) -> List[str]:
        """Extract image URLs with regex."""
        urls = []
        seen = set()

        # <img src="...">
        for m in re.finditer(r'<img[^>]*src=["\']([^"\']+)["\']', text, re.IGNORECASE):
            src = self._resolve_url(m.group(1), base_url)
            if src and src not in seen:
                seen.add(src)
                urls.append(src)
                if len(urls) >= MAX_IMAGES:
                    return urls

        # og:image
        for m in re.finditer(r'<meta[^>]*property=["\']og:image["\'][^>]*content=["\']([^"\']+)["\']', text, re.IGNORECASE):
            src = self._resolve_url(m.group(1), base_url)
            if src and src not in seen:
                seen.add(src)
                urls.append(src)

        return urls

    def _extract_links(self, text: str, base_url: str) -> List[str]:
        """Extract hyperlinks with regex."""
        urls = []
        seen = set()

        for m in re.finditer(r'<a[^>]*href=["\']([^"\']+)["\']', text, re.IGNORECASE):
            href = m.group(1).strip()
            if href.startswith(("javascript:", "mailto:", "tel:", "#")):
                continue
            resolved = self._resolve_url(href, base_url)
            if resolved and resolved not in seen:
                seen.add(resolved)
                urls.append(resolved)
                if len(urls) >= MAX_LINKS:
                    return urls

        return urls

    @staticmethod
    def _resolve_url(href: str, base_url: str) -> str:
        if not href:
            return ""
        resolved = urljoin(base_url, href)
        try:
            parsed = urlparse(resolved)
            clean = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            if parsed.query:
                clean += f"?{parsed.query}"
            return clean
        except Exception:
            return resolved
