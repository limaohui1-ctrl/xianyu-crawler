"""
JSON parser — handles JSON API responses and plain JSON content.

When a page returns JSON (API endpoints, JSON files), this parser
extracts structured fields directly from the JSON object.
"""

import json
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from acs.core.result_model import ParseResult
from acs.fetcher.response_classifier import ContentType
from acs.parser.parser_engine import BaseParser


class JsonParser(BaseParser):
    """Parse JSON API responses or raw JSON content."""

    name = "json"

    def can_handle(self, content_type: ContentType, body: str) -> bool:
        return content_type == ContentType.JSON

    def parse(self, url: str, body: str, **kwargs) -> ParseResult:
        result = ParseResult(url=url, parser_used="json")

        try:
            data = json.loads(body)
        except json.JSONDecodeError as e:
            result.error = f"JSON parse error: {e}"
            result.error_category = "parse_invalid_json"
            result.build()
            return result

        result.raw_json = data
        result.structured_data = self._flatten_to_list(data)

        # Walk the JSON tree to find common fields
        self._walk_json(data, result)

        result.build()
        return result

    def _flatten_to_list(self, data: Any, depth: int = 0) -> List[dict]:
        """Recursively flatten JSON to a list of dict items for structured_data."""
        if depth > 10:
            return []
        if isinstance(data, list):
            items = []
            for item in data[:50]:
                items.extend(self._flatten_to_list(item, depth + 1))
            return items
        if isinstance(data, dict):
            # Check for @type → this is JSON-LD
            if "@type" in data:
                return [data]
            # Check for common list wrappers
            for key in ("data", "items", "results", "records", "products", "list"):
                val = data.get(key)
                if isinstance(val, list):
                    return self._flatten_to_list(val, depth + 1)
            return [data]
        return []

    def _walk_json(self, obj: Any, result: ParseResult, prefix: str = ""):
        """Walk through JSON and populate Result fields by key name matching."""
        if isinstance(obj, dict):
            for key, value in obj.items():
                key_lower = key.lower().strip()

                # Title
                if key_lower in ("title", "name", "headline", "subject") and not result.title:
                    if isinstance(value, str) and value.strip():
                        result.title = value[:500]

                # Author
                if key_lower in ("author", "creator", "publisher", "seller", "username",
                                 "owner", "postedby") and not result.author:
                    if isinstance(value, str) and value.strip():
                        result.author = value[:200]
                    elif isinstance(value, dict):
                        result.author = value.get("name", "") or value.get("username", "") or ""

                # Price
                if key_lower in ("price", "amount", "cost", "saleprice", "priceamount",
                                 "unitprice", "listprice") and not result.price:
                    if isinstance(value, (int, float)):
                        result.price = str(value)
                    elif isinstance(value, str) and value.strip():
                        result.price = value[:60]
                    elif isinstance(value, dict):
                        result.price = str(value.get("amount", value.get("value", "")))

                # Published time
                if key_lower in ("published_time", "publishedtime", "pubdate", "datepublished",
                                 "created_at", "createdat", "created", "date", "timestamp",
                                 "publishdate", "postdate", "updated_at") and not result.published_time:
                    if isinstance(value, str) and value.strip():
                        result.published_time = value[:100]

                # Body / description
                if key_lower in ("body", "content", "description", "text", "summary",
                                 "detail", "fulltext", "message", "overview") and not result.body:
                    if isinstance(value, str) and value.strip():
                        result.body = value[:20000]

                # Images
                if key_lower in ("image", "images", "photo", "photos", "thumbnail", "avatar",
                                 "picture", "pictures", "cover", "screenshot"):
                    self._collect_images(value, result)

                # Recurse
                if isinstance(value, (dict, list)):
                    self._walk_json(value, result, f"{prefix}.{key}")

        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                if i > 200:
                    break
                self._walk_json(item, result, f"{prefix}[{i}]")

    def _collect_images(self, value: Any, result: ParseResult):
        """Collect image URLs from various JSON shapes."""
        seen = set(result.images)

        def _add(url_candidate):
            if not url_candidate or not isinstance(url_candidate, str):
                return
            url_candidate = url_candidate.strip()
            if url_candidate in seen:
                return
            if url_candidate.startswith(("http://", "https://", "//")):
                if url_candidate.startswith("//"):
                    url_candidate = "https:" + url_candidate
                result.images.append(url_candidate)
                seen.add(url_candidate)

        if isinstance(value, str):
            _add(value)
        elif isinstance(value, list):
            for item in value[:50]:
                if isinstance(item, str):
                    _add(item)
                elif isinstance(item, dict):
                    _add(item.get("url", "") or item.get("src", "") or item.get("href", ""))
        elif isinstance(value, dict):
            _add(value.get("url", "") or value.get("src", "") or value.get("href", ""))
