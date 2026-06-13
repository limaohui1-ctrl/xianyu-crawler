"""
XPath-based parser — secondary HTML parser using lxml's XPath support.

This parser is tried when the CSS parser is available but we want a
different extraction strategy.  XPath is particularly useful for:
  - Extracting elements by exact position
  - Complex conditional matching
  - Namespace-aware document traversal

Uses lxml for parsing (faster and more XPath-capable than BeautifulSoup).
"""

from typing import List, Optional, Tuple
from urllib.parse import urljoin, urlparse
import re

from acs.core.result_model import ParseResult, PageImage, PageLink, PageTable
from acs.fetcher.response_classifier import ContentType
from acs.parser.parser_engine import BaseParser


MAX_TEXT_LENGTH = 20000
MAX_IMAGES = 120
MAX_LINKS = 300


def _compact_text(text, limit=MAX_TEXT_LENGTH):
    if not text:
        return ""
    text = re.sub(r"[\r\t]+", " ", str(text))
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)
    return text.strip()[:limit]


def _normalize_src(src: str, base_url: str) -> str:
    if not src:
        return ""
    resolved = urljoin(base_url, src)
    try:
        parsed = urlparse(resolved)
        clean = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        if parsed.query:
            clean += f"?{parsed.query}"
        return clean
    except Exception:
        return resolved


class XPathParser(BaseParser):
    """Extract content from HTML using XPath selectors (via lxml)."""

    name = "xpath"

    def can_handle(self, content_type: ContentType, body: str) -> bool:
        return content_type == ContentType.HTML

    def parse(self, url: str, body: str, **kwargs) -> ParseResult:
        try:
            from lxml import etree, html
        except ImportError:
            # lxml not installed — return empty result
            result = ParseResult(url=url, parser_used="xpath")
            result.warnings.append(
                type("ParseWarning", (), {"code": "LXML_MISSING", "message": "lxml not installed — XPath parser skipped", "field": ""})()
            )
            result.build()
            return result

        # Parse with lxml
        try:
            doc = html.fromstring(body.encode("utf-8", errors="replace"))
        except Exception:
            # Try as string
            doc = html.fromstring(body)

        result = ParseResult(url=url, parser_used="xpath")

        result.title = self._xpath_text(doc, '//h1', fallback='//title')
        result.author = self._xpath_text(doc,
            '//meta[@name="author"]/@content',
            fallback='//*[contains(@class,"author")]')
        result.published_time = self._xpath_text(doc,
            '//meta[@property="article:published_time"]/@content',
            fallback='//time[@datetime]/@datetime')

        # Price — look for currency patterns
        price_elems = doc.xpath('//*[contains(@class,"price") or contains(@id,"price")]')
        for elem in price_elems[:5]:
            text = _compact_text(
                "".join(elem.itertext()) if hasattr(elem, "itertext") else str(elem.text or ""),
                200,
            )
            if re.search(r'[¥$€£￥]\s*\d+|\d+\.?\d*\s*[元]', text):
                result.price = text
                break

        # Body — main content areas
        for xpath in [
            '//article', '//main', '//*[@role="main"]',
            '//div[contains(@class,"content")]', '//div[contains(@class,"article")]',
        ]:
            elems = doc.xpath(xpath)
            if elems:
                text = "".join(
                    elems[0].itertext() if hasattr(elems[0], "itertext") else str(elems[0].text or "")
                )
                if len(text.strip()) > 100:
                    result.body = _compact_text(text)
                    break
        if not result.body:
            body_elems = doc.xpath('//body')
            if body_elems:
                result.body = _compact_text(
                    "".join(body_elems[0].itertext() if hasattr(body_elems[0], "itertext")
                           else str(body_elems[0].text or ""))
                )

        # Images
        seen = set()
        for img in doc.xpath('//img[@src]'):
            src = _normalize_src(img.get("src", ""), url)
            if not src or src in seen:
                continue
            seen.add(src)
            alt = img.get("alt", "")[:200]
            result.images.append(src)
            result.page_images.append(PageImage(src=src, alt=alt))
            if len(seen) >= MAX_IMAGES:
                break

        # Links
        base_domain = urlparse(url).netloc.lower()
        seen_links = set()
        for a in doc.xpath('//a[@href]'):
            href = a.get("href", "").strip()
            if not href or href.startswith(("javascript:", "mailto:", "tel:", "#")):
                continue
            resolved = _normalize_src(href, url)
            if not resolved or resolved in seen_links:
                continue
            seen_links.add(resolved)
            text = _compact_text(
                "".join(a.itertext() if hasattr(a, "itertext") else a.text or ""), 120
            )
            is_internal = urlparse(resolved).netloc.lower() == base_domain
            result.links.append(resolved)
            result.page_links.append(PageLink(url=resolved, text=text, is_internal=is_internal))
            if len(seen_links) >= MAX_LINKS:
                break

        # Tables
        for table in doc.xpath('//table'):
            headers = []
            for th in table.xpath('.//th'):
                headers.append(_compact_text(
                    "".join(th.itertext() if hasattr(th, "itertext") else th.text or ""), 100
                ))
            rows = []
            for tr in table.xpath('.//tr'):
                cells = []
                for td in tr.xpath('./td'):
                    cells.append(_compact_text(
                        "".join(td.itertext() if hasattr(td, "itertext") else td.text or ""), 500
                    ))
                if cells and not tr.xpath('./th'):
                    rows.append(cells)
                    if len(rows) >= 200:
                        break
            if headers or rows:
                pt = PageTable(headers=headers, rows=rows)
                result.page_tables.append(pt)
                result.tables.append(pt.to_text())

        result.build()
        return result

    def _xpath_text(self, doc, xpath: str, fallback: str = "") -> str:
        """Extract text from the first matching XPath, with fallback."""
        results = doc.xpath(xpath)
        if results:
            first = results[0]
            if hasattr(first, "itertext"):
                text = "".join(first.itertext())
            elif hasattr(first, "text"):
                text = first.text or ""
            else:
                text = str(first)
            if text and text.strip():
                return _compact_text(text, 500)
        if fallback:
            fb_results = doc.xpath(fallback)
            if fb_results:
                first = fb_results[0]
                if hasattr(first, "itertext"):
                    text = "".join(first.itertext())
                elif hasattr(first, "text"):
                    text = first.text or ""
                else:
                    text = str(first)
                return _compact_text(text, 500)
        return ""
