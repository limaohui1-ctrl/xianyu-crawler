"""
Deduplication — URL-based and content-hash-based dedup for crawl results.

Two levels of dedup:
  1. URL dedup: prevents re-fetching the same URL within a session/window
  2. Content dedup: detects duplicate content across different URLs using
     content hash (e.g., mirror sites, pagination landing pages)

Both use in-memory sets + optional persistent backing via SQLite.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse, parse_qs
import hashlib
import re
import threading
import time

from acs.core.result_model import ParseResult


# ── URL normalization for dedup ──────────────────────────────────

# Common tracking/analytics query params to strip
_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "gclsrc", "dclid", "msclkid", "twclid",
    "ref", "source", "mc_cid", "mc_eid", "_ga", "_gl",
    "ck_subscriber_id", "oly_anon_id", "oly_enc_id",
    "_openstat", "vero_id", "wickedid", "yclid",
    "_hsenc", "_hsmi", "hsCtaTracking",
    "spm", "scm", "tracking", "trk", "campaign_id",
}


def normalize_url_for_dedup(url: str) -> str:
    """Normalize a URL for deduplication.

    - Lowercase scheme + host
    - Strip fragment (#...)
    - Strip tracking query params
    - Sort remaining query params (where safe)
    - Strip trailing slash on path
    """
    if not url:
        return ""

    try:
        parsed = urlparse(url)
    except Exception:
        return url.lower().strip()

    # Lowercase scheme + host
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()

    # Path: strip trailing slash (except root)
    path = parsed.path
    if path.endswith("/") and len(path) > 1:
        path = path.rstrip("/")

    # Query: strip tracking params, sort remaining
    query = ""
    if parsed.query:
        try:
            params = parse_qs(parsed.query, keep_blank_values=True)
            # Remove tracking params
            clean_params = {}
            for k, v in params.items():
                if k.lower() not in _TRACKING_PARAMS:
                    clean_params[k] = v
            if clean_params:
                # Sort by key for consistent ordering
                parts = []
                for k in sorted(clean_params.keys()):
                    for val in clean_params[k]:
                        parts.append(f"{k}={val}")
                query = "&".join(parts)
        except Exception:
            query = parsed.query

    result = f"{scheme}://{netloc}{path}"
    if query:
        result += f"?{query}"

    return result


# ── Content hash (for content dedup) ────────────────────────────

def content_dedup_key(result: ParseResult) -> str:
    """Generate a content-based dedup key from a ParseResult.

    Uses only semantic fields (title, body, price, author) — NOT metadata
    like URL or timestamp.  This way, the same content on different URLs
    will match.
    """
    parts = [
        result.title or "",
        result.body or "",
        result.price or "",
        result.author or "",
        result.published_time or "",
    ]
    canonical = "|".join(p.strip()[:2000] for p in parts)
    return hashlib.sha256(canonical.encode("utf-8", errors="ignore")).hexdigest()


# ── Dedup store ──────────────────────────────────────────────────

class DedupStore:
    """Thread-safe deduplication store with optional persistence.

    Supports:
      - URL-level dedup (normalized URL)
      - Content-level dedup (content hash)

    Usage:
        store = DedupStore()
        if store.is_url_duplicate("https://example.com/page"):
            print("Already scraped")
        store.mark_url("https://example.com/page")

        if store.is_content_duplicate(result):
            print("Content already seen")
        store.mark_content(result)
    """

    def __init__(self, max_urls: int = 50000, max_hashes: int = 20000,
                 ttl_seconds: float = 86400.0):  # 24h default
        self._url_set: Set[str] = set()
        self._hash_set: Set[str] = set()
        self._url_timestamps: Dict[str, float] = {}
        self._hash_timestamps: Dict[str, float] = {}
        self._lock = threading.Lock()
        self.max_urls = max_urls
        self.max_hashes = max_hashes
        self.ttl_seconds = ttl_seconds
        self._url_count = 0
        self._hash_count = 0
        self._duplicate_url_count = 0
        self._duplicate_content_count = 0

    # ── URL dedup ──

    def is_url_duplicate(self, url: str) -> bool:
        """Check if a URL has already been processed."""
        key = normalize_url_for_dedup(url)
        with self._lock:
            if key in self._url_set:
                # Check TTL
                ts = self._url_timestamps.get(key, 0)
                if time.time() - ts > self.ttl_seconds:
                    # Expired — remove
                    self._url_set.discard(key)
                    self._url_timestamps.pop(key, None)
                    return False
                return True
            return False

    def mark_url(self, url: str):
        """Mark a URL as processed."""
        key = normalize_url_for_dedup(url)
        with self._lock:
            # Evict oldest if at capacity
            while len(self._url_set) >= self.max_urls:
                oldest = min(self._url_timestamps, key=self._url_timestamps.get, default=None)
                if oldest:
                    self._url_set.discard(oldest)
                    self._url_timestamps.pop(oldest, None)
                else:
                    break
            self._url_set.add(key)
            self._url_timestamps[key] = time.time()
            self._url_count += 1

    def mark_url_duplicate(self, url: str):
        """Record that a URL was skipped as duplicate."""
        with self._lock:
            self._duplicate_url_count += 1

    # ── Content dedup ──

    def is_content_duplicate(self, result: ParseResult) -> bool:
        """Check if content with the same hash has already been seen."""
        key = content_dedup_key(result)
        with self._lock:
            if key in self._hash_set:
                ts = self._hash_timestamps.get(key, 0)
                if time.time() - ts > self.ttl_seconds:
                    self._hash_set.discard(key)
                    self._hash_timestamps.pop(key, None)
                    return False
                return True
            return False

    def mark_content(self, result: ParseResult):
        """Mark content hash as seen."""
        key = content_dedup_key(result)
        with self._lock:
            while len(self._hash_set) >= self.max_hashes:
                oldest = min(self._hash_timestamps, key=self._hash_timestamps.get, default=None)
                if oldest:
                    self._hash_set.discard(oldest)
                    self._hash_timestamps.pop(oldest, None)
                else:
                    break
            self._hash_set.add(key)
            self._hash_timestamps[key] = time.time()
            self._hash_count += 1

    def mark_content_duplicate(self, result: ParseResult):
        """Record that content was skipped as duplicate."""
        with self._lock:
            self._duplicate_content_count += 1

    # ── Queries ──

    @property
    def url_set_size(self) -> int:
        with self._lock:
            return len(self._url_set)

    @property
    def hash_set_size(self) -> int:
        with self._lock:
            return len(self._hash_set)

    @property
    def stats(self) -> dict:
        with self._lock:
            return {
                "urls_seen": self._url_count,
                "urls_in_set": len(self._url_set),
                "url_duplicates_skipped": self._duplicate_url_count,
                "content_hashes_stored": self._hash_count,
                "content_hashes_in_set": len(self._hash_set),
                "content_duplicates_skipped": self._duplicate_content_count,
                "ttl_seconds": self.ttl_seconds,
            }

    def clear(self):
        """Reset all state."""
        with self._lock:
            self._url_set.clear()
            self._hash_set.clear()
            self._url_timestamps.clear()
            self._hash_timestamps.clear()
            self._url_count = 0
            self._hash_count = 0
            self._duplicate_url_count = 0
            self._duplicate_content_count = 0
