"""
AI response cache with LRU eviction and TTL — reduces duplicate API calls.
Also provides URL-level dedup to prevent re-scraping the same URL within a TTL window.

Thread-safe.  All state guarded by locks.

Usage:
    from core_cache import get_ai_cache, ai_cache_key

    cache = get_ai_cache()
    key = ai_cache_key(system_prompt, user_prompt, model, temperature)
    cached = cache.get(key)
    if cached:
        return cached                    # cache hit — skip API call
    result = call_api(...)
    cache.set(key, result)              # cache the result
"""

import hashlib
import json
import os
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


# ═══════════════════════════════════════════════════════════════════
# Cache entry
# ═══════════════════════════════════════════════════════════════════

@dataclass
class CacheEntry:
    key: str
    value: Any
    created_at: float = field(default_factory=time.time)
    ttl_seconds: float = 3600.0
    hit_count: int = 0


# ═══════════════════════════════════════════════════════════════════
# LRU Cache (thread-safe, TTL-aware)
# ═══════════════════════════════════════════════════════════════════

class LRUCache:
    """Thread-safe LRU cache with per-entry TTL.

    Entries expire after *default_ttl* seconds (configurable per-set).
    When the cache reaches *max_size*, the least-recently-used entry is evicted.
    """

    def __init__(self, max_size: int = 500, default_ttl: float = 3600.0):
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._store: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    # ── Core API ────────────────────────────────────────────────

    def get(self, key: str) -> Optional[Any]:
        """Return the cached value for *key*, or None if missing / expired."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._misses += 1
                return None
            if time.time() - entry.created_at > entry.ttl_seconds:
                del self._store[key]
                self._misses += 1
                return None
            # Move to end (most-recently-used)
            self._store.move_to_end(key)
            entry.hit_count += 1
            self._hits += 1
            return entry.value

    def set(self, key: str, value: Any, ttl: Optional[float] = None):
        """Store *value* under *key*.  Evicts LRU entry if at capacity."""
        ttl = ttl if ttl is not None else self.default_ttl
        with self._lock:
            if key in self._store:
                self._store.move_to_end(key)
                entry = self._store[key]
                entry.value = value
                entry.created_at = time.time()
                entry.ttl_seconds = ttl
                return
            while len(self._store) >= self.max_size:
                self._store.popitem(last=False)
                self._evictions += 1
            self._store[key] = CacheEntry(
                key=key, value=value, ttl_seconds=ttl,
            )

    def has(self, key: str) -> bool:
        """Check existence without affecting LRU order or hit counters."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return False
            if time.time() - entry.created_at > entry.ttl_seconds:
                del self._store[key]
                return False
            return True

    def remove(self, key: str):
        with self._lock:
            self._store.pop(key, None)

    def clear(self):
        with self._lock:
            self._store.clear()
            self._hits = 0
            self._misses = 0
            self._evictions = 0

    # ── Introspection ───────────────────────────────────────────

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._store)

    @property
    def stats(self) -> Dict[str, Any]:
        with self._lock:
            total = self._hits + self._misses
            return {
                "size": len(self._store),
                "max_size": self.max_size,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(self._hits / max(total, 1), 4),
                "evictions": self._evictions,
                "default_ttl_s": self.default_ttl,
            }


# ═══════════════════════════════════════════════════════════════════
# Cache key builders
# ═══════════════════════════════════════════════════════════════════

def ai_cache_key(system_prompt: str, user_prompt: str,
                 model: str, temperature: float,
                 base_url: str = "", api_key_hash: str = "") -> str:
    """Deterministic hash for an AI chat-completion call.

    Includes base_url and a hash of the API key so different providers /
    different keys to the same endpoint never share cache."""
    payload = f"{system_prompt}|||{user_prompt}|||{model}|||{temperature}|||{base_url}|||{api_key_hash}"
    return hashlib.sha256(payload.encode("utf-8", errors="ignore")).hexdigest()


def ai_transform_cache_key(records_text: str, instruction: str,
                           model: str, temperature: float) -> str:
    """Deterministic hash for an AI transform/clean call."""
    payload = f"{records_text}|||{instruction}|||{model}|||{temperature}"
    return hashlib.sha256(payload.encode("utf-8", errors="ignore")).hexdigest()


def url_dedup_key(url: str, template_name: str = "") -> str:
    """Deterministic dedup key for a URL + template combination."""
    payload = f"{url}|||{template_name}"
    return hashlib.sha256(payload.encode("utf-8", errors="ignore")).hexdigest()


def firecrawl_scrape_key(url: str, formats: str = "") -> str:
    """Deterministic dedup key for a Firecrawl scrape call."""
    payload = f"scrape|||{url}|||{formats}"
    return hashlib.sha256(payload.encode("utf-8", errors="ignore")).hexdigest()


# ═══════════════════════════════════════════════════════════════════
# Global singletons
# ═══════════════════════════════════════════════════════════════════

_ai_cache: Optional[LRUCache] = None
_url_dedup_cache: Optional[LRUCache] = None
_firecrawl_cache: Optional[LRUCache] = None
_cache_lock = threading.Lock()

# Default TTLs — configurable
AI_CACHE_DEFAULT_TTL = 3600.0        # 1 hour — same prompt rarely needs re-fetching
AI_CACHE_MAX_SIZE = 500
URL_DEDUP_TTL = 86400.0              # 24 hours — same URL same day = duplicate
URL_DEDUP_MAX_SIZE = 5000
FIRECRAWL_CACHE_TTL = 1800.0         # 30 minutes — scrape results are semi-stable
FIRECRAWL_CACHE_MAX_SIZE = 1000


def get_ai_cache() -> LRUCache:
    """Return the singleton AI response cache."""
    global _ai_cache
    if _ai_cache is None:
        with _cache_lock:
            if _ai_cache is None:
                _ai_cache = LRUCache(
                    max_size=AI_CACHE_MAX_SIZE,
                    default_ttl=AI_CACHE_DEFAULT_TTL,
                )
    return _ai_cache


def get_url_dedup_cache() -> LRUCache:
    """Return the singleton URL dedup cache."""
    global _url_dedup_cache
    if _url_dedup_cache is None:
        with _cache_lock:
            if _url_dedup_cache is None:
                _url_dedup_cache = LRUCache(
                    max_size=URL_DEDUP_MAX_SIZE,
                    default_ttl=URL_DEDUP_TTL,
                )
    return _url_dedup_cache


def get_firecrawl_cache() -> LRUCache:
    """Return the singleton Firecrawl scrape cache."""
    global _firecrawl_cache
    if _firecrawl_cache is None:
        with _cache_lock:
            if _firecrawl_cache is None:
                _firecrawl_cache = LRUCache(
                    max_size=FIRECRAWL_CACHE_MAX_SIZE,
                    default_ttl=FIRECRAWL_CACHE_TTL,
                )
    return _firecrawl_cache


def reset_caches():
    """Reset all caches (for tests)."""
    global _ai_cache, _url_dedup_cache, _firecrawl_cache
    with _cache_lock:
        _ai_cache = None
        _url_dedup_cache = None
        _firecrawl_cache = None


def all_cache_stats() -> dict:
    """Return a diagnostic snapshot of all caches."""
    return {
        "ai": get_ai_cache().stats,
        "url_dedup": get_url_dedup_cache().stats,
        "firecrawl": get_firecrawl_cache().stats,
    }
