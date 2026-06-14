"""
CSS selector-based parser — the primary parser for HTML pages.

Extracts content using CSS selectors (via BeautifulSoup).  This is the
most commonly used parser and handles title, body, images, links, tables,
and metadata extraction from standard HTML pages.
"""

from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse
from html import unescape
import re
import json

from bs4 import BeautifulSoup, Tag

from acs.core.result_model import ParseResult, PageImage, PageLink, PageTable, ParseWarning
from acs.fetcher.response_classifier import ContentType
from acs.parser.parser_engine import BaseParser


MAX_TEXT_LENGTH = 20000
MAX_IMAGES = 120
MAX_LINKS = 300
MAX_TABLE_ROWS = 200


def _compact_text(text, limit=MAX_TEXT_LENGTH):
    """Strip excessive whitespace and truncate."""
    if not text:
        return ""
    text = re.sub(r"[\r\t]+", " ", str(text))
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)
    return text.strip()[:limit]


def _safe_tag_text(tag: Tag) -> str:
    """Get text from a tag, handling None."""
    if tag is None:
        return ""
    return tag.get_text(" ", strip=True)


def _normalize_src(src: str, base_url: str) -> str:
    """Resolve relative URLs and strip fragments."""
    if not src:
        return ""
    resolved = urljoin(base_url, src)
    # Strip fragment
    try:
        parsed = urlparse(resolved)
        clean = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        if parsed.query:
            clean += f"?{parsed.query}"
        return clean
    except Exception:
        return resolved


class CssParser(BaseParser):
    """Extract content from HTML using CSS selectors."""

    name = "css"

    def can_handle(self, content_type: ContentType, body: str) -> bool:
        return content_type == ContentType.HTML

    def parse(self, url: str, body: str, **kwargs) -> ParseResult:
        soup = BeautifulSoup(body or "", "html.parser")

        # Remove noise
        for tag in soup(["script", "style", "noscript", "svg", "canvas", "iframe"]):
            tag.decompose()

        result = ParseResult(url=url, parser_used="css")

        # ── Title ──
        result.title = self._extract_title(soup)

        # ── Metadata ──
        metadata = self._extract_metadata(soup, url)

        # ── Author ──
        result.author = self._extract_author(soup, metadata)

        # ── Published time ──
        result.published_time = self._extract_time(soup, metadata)

        # ── Price ──
        result.price = self._extract_price(soup, metadata)

        # ── Body ──
        result.body = self._extract_body(soup)

        # ── Images ──
        result.images, result.page_images = self._extract_images(soup, url)

        # ── Links ──
        result.links, result.page_links = self._extract_links(soup, url)

        # ── Tables ──
        result.tables, result.page_tables = self._extract_tables(soup)

        # ── Metadata ──
        result.metadata = metadata

        result.build()
        return result

    # ── Individual extractors ──────────────────────────────────

    def _extract_title(self, soup: BeautifulSoup) -> str:
        """Extract title: h1 > og:title > <title>."""
        priority = [
            lambda: soup.select_one("h1"),
            lambda: soup.select_one('meta[property="og:title"]'),
            lambda: soup.select_one('meta[name="twitter:title"]'),
            lambda: soup.title,
        ]
        for getter in priority:
            tag = getter()
            if tag is None:
                continue
            if isinstance(tag, Tag) and tag.name == "meta":
                content = tag.get("content", "")
                if content:
                    return _compact_text(content, 500)
            elif isinstance(tag, Tag):
                text = tag.get_text(" ", strip=True)
                if text:
                    return _compact_text(text, 500)
        return ""

    def _extract_metadata(self, soup: BeautifulSoup, base_url: str) -> dict:
        """Extract <meta> tags."""
        meta = {}
        mapping = {
            "description": ['meta[name="description"]', 'meta[property="og:description"]'],
            "keywords": ['meta[name="keywords"]'],
            "og_image": ['meta[property="og:image"]'],
            "og_site_name": ['meta[property="og:site_name"]'],
            "og_type": ['meta[property="og:type"]'],
            "canonical": ['link[rel="canonical"]'],
        }
        for key, selectors in mapping.items():
            for sel in selectors:
                tag = soup.select_one(sel)
                if tag is None:
                    continue
                if tag.name == "link":
                    value = tag.get("href", "")
                else:
                    value = tag.get("content", "")
                if value:
                    if key in ("og_image", "canonical"):
                        value = _normalize_src(value, base_url)
                    meta[key] = _compact_text(value, 1000)
                    break
        return meta

    def _extract_author(self, soup: BeautifulSoup, metadata: dict) -> str:
        """Extract author: meta > schema > byline patterns."""
        # meta author
        for sel in ['meta[name="author"]', 'meta[property="article:author"]']:
            tag = soup.select_one(sel)
            if tag and tag.get("content"):
                return _compact_text(tag["content"], 200)

        # Common author selectors
        for sel in [
            '[class*="author"]', '[class*="byline"]', '[rel="author"]',
            '[itemprop="author"]', '.post-author', '.entry-author',
            'a[href*="/author/"]', 'a[href*="/users/"]',
        ]:
            tag = soup.select_one(sel)
            if tag:
                return _compact_text(tag.get_text(" ", strip=True), 200)

        return ""

    def _extract_time(self, soup: BeautifulSoup, metadata: dict) -> str:
        """Extract published/modified time."""
        # meta tags
        for sel in [
            'meta[property="article:published_time"]',
            'meta[property="article:modified_time"]',
            'meta[name="pubdate"]',
            'meta[name="publish_date"]',
            'meta[name="date"]',
        ]:
            tag = soup.select_one(sel)
            if tag and tag.get("content"):
                return _compact_text(tag["content"], 100)

        # <time> elements
        for sel in ['time[datetime]', 'time[pubdate]', '[class*="publish"] time']:
            tag = soup.select_one(sel)
            if tag:
                dt = tag.get("datetime", "") or tag.get_text(" ", strip=True)
                if dt:
                    return _compact_text(dt, 100)

        # itemprop
        for sel in ['[itemprop="datePublished"]', '[itemprop="dateModified"]']:
            tag = soup.select_one(sel)
            if tag:
                dt = tag.get("datetime", "") or tag.get("content", "") or tag.get_text(" ", strip=True)
                if dt:
                    return _compact_text(dt, 100)

        return ""

    def _extract_price(self, soup: BeautifulSoup, metadata: dict) -> str:
        """Extract price."""

        # meta price
        for sel in [
            'meta[property="product:price:amount"]',
            'meta[property="og:price:amount"]',
            'meta[name="price"]',
        ]:
            tag = soup.select_one(sel)
            if tag and tag.get("content"):
                return _compact_text(tag["content"], 60)

        # itemprop="price"
        tag = soup.select_one('[itemprop="price"]')
        if tag:
            price = tag.get("content", "") or tag.get_text(" ", strip=True)
            if price:
                return _compact_text(price, 60)

        # Common price class selectors
        for sel in [
            '[class*="price"]', '[class*="Price"]', '[id*="price"]',
            '[data-price]', '.product-price', '.sale-price',
            '[class*="amount"]', '[class*="cost"]',
        ]:
            tags = soup.select(sel)
            for tag in tags[:5]:
                text = tag.get_text(" ", strip=True)
                # Look for currency symbols + numbers
                if re.search(r'[¥$€£￥]\s*\d+', text):
                    return _compact_text(text, 60)
                if re.search(r'\d+\.?\d*\s*[元]', text):
                    return _compact_text(text, 60)

        return ""

    def _extract_body(self, soup: BeautifulSoup) -> str:
        """Extract main body content."""
        # Try article/main first
        for sel in ['article', 'main', '[role="main"]', '.post-content', '.article-content',
                     '.entry-content', '#content', '.content', '[class*="article-body"]']:
            tag = soup.select_one(sel)
            if tag and len(tag.get_text(" ", strip=True)) > 100:
                return _compact_text(tag.get_text("\n", strip=True))

        # Fall back to body
        body_tag = soup.body
        if body_tag:
            return _compact_text(body_tag.get_text("\n", strip=True))
        return ""

    def _extract_images(self, soup: BeautifulSoup, base_url: str) -> tuple[List[str], List[PageImage]]:
        """Extract image URLs."""
        urls = []
        page_images = []
        seen = set()

        for img in soup.select("img[src]"):
            src = _normalize_src(img.get("src", ""), base_url)
            if not src or src in seen:
                continue
            seen.add(src)
            alt = _compact_text(img.get("alt", ""), 200)
            urls.append(src)
            page_images.append(PageImage(src=src, alt=alt))
            if len(seen) >= MAX_IMAGES:
                break

        return urls, page_images

    def _extract_links(self, soup: BeautifulSoup, base_url: str) -> tuple[List[str], List[PageLink]]:
        """Extract hyperlinks."""
        urls = []
        page_links = []
        seen = set()

        base_domain = urlparse(base_url).netloc.lower()

        for a in soup.select("a[href]"):
            href = a.get("href", "").strip()
            if not href or href.startswith(("javascript:", "mailto:", "tel:", "#")):
                continue
            resolved = _normalize_src(href, base_url)
            if not resolved or resolved in seen:
                continue
            seen.add(resolved)
            text = _compact_text(a.get_text(" ", strip=True), 120)
            is_internal = urlparse(resolved).netloc.lower() == base_domain
            urls.append(resolved)
            page_links.append(PageLink(url=resolved, text=text, is_internal=is_internal))
            if len(seen) >= MAX_LINKS:
                break

        return urls, page_links

    def _extract_tables(self, soup: BeautifulSoup) -> tuple[List[str], List[PageTable]]:
        """Extract HTML tables."""
        texts = []
        page_tables = []

        for table in soup.select("table"):
            caption_tag = table.select_one("caption")
            caption = _compact_text(caption_tag.get_text(" ", strip=True), 200) if caption_tag else ""

            # Headers
            headers = []
            for th in table.select("thead th, tr:first-child th"):
                headers.append(_compact_text(th.get_text(" ", strip=True), 100))
            if not headers:
                for th in table.select("th"):
                    headers.append(_compact_text(th.get_text(" ", strip=True), 100))

            # Rows
            rows = []
            for tr in table.select("tbody tr, tr"):
                # Skip header rows
                if tr.select_one("th") and not rows:
                    continue
                cells = []
                for td in tr.select("td"):
                    cells.append(_compact_text(td.get_text(" ", strip=True), 500))
                if cells:
                    rows.append(cells)
                if len(rows) >= MAX_TABLE_ROWS:
                    break

            if not headers and not rows:
                continue

            pt = PageTable(headers=headers, rows=rows, caption=caption)
            page_tables.append(pt)
            texts.append(pt.to_text())

        return texts, page_tables
