"""
JSON-LD structured data parser — extracts Schema.org / JSON-LD from HTML pages.

JSON-LD is embedded in <script type="application/ld+json"> tags and provides
rich structured data (Product, Article, Organization, Event, etc.).
This parser extracts that data and maps it to the unified ParseResult schema.
"""

from typing import Any, Dict, List, Optional
import json
import re

from bs4 import BeautifulSoup

from acs.core.result_model import ParseResult
from acs.fetcher.response_classifier import ContentType
from acs.parser.parser_engine import BaseParser


# ── Known JSON-LD @type → field mappings ────────────────────────

_TYPE_FIELD_MAP = {
    "name": ("title",),
    "headline": ("title",),
    "description": ("body",),
    "articleBody": ("body",),
    "text": ("body",),
    "author": ("author",),
    "creator": ("author",),
    "seller": ("author",),
    "brand": ("author",),
    "price": ("price",),
    "offers": ("price",),
    "datePublished": ("published_time",),
    "dateModified": ("published_time",),
    "dateCreated": ("published_time",),
    "startDate": ("published_time",),
    "image": ("images",),
    "thumbnailUrl": ("images",),
    "url": (),
    "mainEntityOfPage": (),
}


def _flatten_jsonld(data: Any, depth: int = 0) -> List[dict]:
    """Recursively extract dict items from JSON-LD (handles @graph, arrays, nested objects)."""
    if depth > 10:
        return []
    if isinstance(data, list):
        items = []
        for item in data:
            items.extend(_flatten_jsonld(item, depth + 1))
        return items
    if isinstance(data, dict):
        graph = data.get("@graph")
        if isinstance(graph, list):
            items = []
            for item in graph:
                items.extend(_flatten_jsonld(item, depth + 1))
            return items
        return [data]
    return []


def _extract_value(value: Any) -> str:
    """Extract a readable string from a JSON-LD value (which may be a string, dict, or list)."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, dict):
        return value.get("name", "") or value.get("@id", "") or json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        parts = []
        for v in value[:10]:
            extracted = _extract_value(v)
            if extracted:
                parts.append(extracted)
        return "、".join(parts)
    return str(value)


class JsonLdParser(BaseParser):
    """Extract structured data from <script type="application/ld+json"> blocks."""

    name = "jsonld"

    def can_handle(self, content_type: ContentType, body: str) -> bool:
        """Can handle HTML (extracting embedded JSON-LD) and JSON directly."""
        return content_type in (ContentType.HTML, ContentType.JSON)

    def parse(self, url: str, body: str, **kwargs) -> ParseResult:
        result = ParseResult(url=url, parser_used="jsonld")

        items: List[dict] = []

        # Try extracting from HTML script tags
        if "<script" in body.lower():
            soup = BeautifulSoup(body, "html.parser")
            for script in soup.select('script[type*="ld+json"]'):
                raw = script.string or script.get_text("", strip=True)
                if not raw:
                    continue
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                items.extend(_flatten_jsonld(payload))
                if len(items) >= 30:
                    break

        # If no items found and body looks like JSON, try direct parse
        if not items and body.strip().startswith(("{", "[")):
            try:
                payload = json.loads(body)
                items = _flatten_jsonld(payload)
            except json.JSONDecodeError:
                pass

        if not items:
            result.error = "No JSON-LD data found"
            result.error_category = "parse_empty"
            result.build()
            return result

        result.structured_data = items

        # Map JSON-LD fields to ParseResult fields (first non-empty wins)
        for item in items:
            if not isinstance(item, dict):
                continue

            item_type = item.get("@type", "")

            # Title: name > headline
            if not result.title:
                for field in ("name", "headline"):
                    val = _extract_value(item.get(field))
                    if val:
                        result.title = val[:500]
                        break

            # Body: description > articleBody > text
            if not result.body:
                for field in ("description", "articleBody", "text", "abstract"):
                    val = _extract_value(item.get(field))
                    if val and len(val) > 20:
                        result.body = val[:20000]
                        break

            # Author: author > creator > seller > brand
            if not result.author:
                for field in ("author", "creator", "seller", "brand", "publisher"):
                    author_val = item.get(field)
                    if author_val is None:
                        continue
                    if isinstance(author_val, dict):
                        result.author = _extract_value(author_val.get("name")) or _extract_value(author_val)
                    else:
                        result.author = _extract_value(author_val)
                    if result.author:
                        result.author = result.author[:200]
                        break

            # Price: price > offers.price > offers.lowPrice
            if not result.price:
                price_val = item.get("price")
                if price_val is not None:
                    result.price = _extract_value(price_val)[:60]
                if not result.price:
                    offers = item.get("offers")
                    if isinstance(offers, dict):
                        result.price = _extract_value(offers.get("price", ""))[:60]
                    elif isinstance(offers, list) and offers:
                        result.price = _extract_value(offers[0].get("price", "") if isinstance(offers[0], dict) else "")

            # Published time
            if not result.published_time:
                for field in ("datePublished", "dateModified", "dateCreated", "startDate", "uploadDate"):
                    val = _extract_value(item.get(field))
                    if val:
                        result.published_time = val[:100]
                        break

            # Images
            img_val = item.get("image")
            if img_val:
                if isinstance(img_val, str):
                    if img_val.startswith(("http://", "https://", "//")):
                        result.images.append(img_val if not img_val.startswith("//") else "https:" + img_val)
                elif isinstance(img_val, dict):
                    src = img_val.get("url", "") or img_val.get("@id", "")
                    if src:
                        result.images.append(src)
                elif isinstance(img_val, list):
                    for img in img_val[:20]:
                        if isinstance(img, str):
                            result.images.append(img)
                        elif isinstance(img, dict):
                            src = img.get("url", "") or img.get("@id", "")
                            if src:
                                result.images.append(src)

            # Thumbnails
            thumb = item.get("thumbnailUrl")
            if thumb and isinstance(thumb, str):
                result.images.append(thumb)

        # Deduplicate images
        result.images = list(dict.fromkeys(result.images))[:120]

        result.build()
        return result
