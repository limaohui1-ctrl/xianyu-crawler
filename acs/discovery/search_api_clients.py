"""SearchApiClients — pluggable real search API clients.

Supported:
  - SearXNG (local Docker, port 8080) — zero API key, multiple engines
  - Bing Web Search API v7 (requires Azure key)
  - DuckDuckGo direct (zero-key fallback)
  - Noop (graceful empty)
  - Mock (demo data)

API keys from env/.env only. Never hardcoded/logged/reported.
"""
import json
import re
import time
import urllib.request
import urllib.error
import urllib.parse
from abc import ABC, abstractmethod
from typing import List, Optional

from .search_api_config import SearchApiConfig, get_search_api_config
from .search_api_provider import SearchApiResult
from .search_api_secret_guard import safe_headers, sanitize_error
from .search_api_quota import SearchApiQuota


class BaseSearchClient(ABC):
    """Abstract base for a real search API client."""

    def __init__(self, config: SearchApiConfig = None, quota: SearchApiQuota = None):
        self.config = config or SearchApiConfig(provider="none")
        self.quota = quota or SearchApiQuota()
        self.last_status = 0
        self.last_error = ""

    @abstractmethod
    def search(self, query: str, limit: int = 20) -> List[SearchApiResult]:
        ...

    @property
    def available(self) -> bool:
        return self.config.enabled and self.quota.check()


class SearXNGSelfHostClient(BaseSearchClient):
    """SearXNG self-hosted (local Docker) — zero API key, multi-engine search.
    
    Requires: docker run -d --name searxng -p 8080:8080 searxng/searxng
    Endpoint: http://127.0.0.1:8080/search?q=...&format=json
    """

    ENDPOINT = "http://127.0.0.1:8080/search"

    def __init__(self, endpoint: str = None):
        import os
        base_url = os.environ.get("ACS_SEARXNG_BASE_URL", "http://127.0.0.1:8080")
        self.endpoint = endpoint or f"{base_url.rstrip('/')}/search"
        cfg = SearchApiConfig(provider="searxng", enabled=True, configured=True)
        super().__init__(cfg)

    def _check_available(self) -> bool:
        try:
            req = urllib.request.Request(self.endpoint + "?q=test&format=json")
            urllib.request.urlopen(req, timeout=5)
            return True
        except Exception:
            return False

    @property
    def available(self) -> bool:
        return self._check_available()

    def search(self, query: str, limit: int = 20) -> List[SearchApiResult]:
        params = {"q": query, "format": "json", "categories": "general",
                  "language": "zh-CN", "pageno": 1}
        url = f"{self.endpoint}?{urllib.parse.urlencode(params)}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ACS/1.2"})
            resp = urllib.request.urlopen(req, timeout=15)
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
            self.last_status = resp.status
            self.quota.record_call(success=True)
            return self._parse_results(data, query, limit)
        except Exception as e:
            self.last_error = sanitize_error(e)
            self.quota.record_call(success=False)
            return []

    def _parse_results(self, data: dict, query: str, limit: int) -> List[SearchApiResult]:
        results = []
        for i, r in enumerate(data.get("results", [])[:limit]):
            url = r.get("url", "")
            if not url:
                continue
            results.append(SearchApiResult(
                url=url,
                title=r.get("title", ""),
                snippet=r.get("content", "") or r.get("snippet", ""),
                source_domain=_extract_domain(url),
                query=query,
                rank=i + 1,
                raw_data={"engine": r.get("engine", "")},
            ))
        return results


class DuckDuckGoDirectClient(BaseSearchClient):
    """DuckDuckGo Lite HTML endpoint — zero API key, always works.
    
    Uses: https://lite.duckduckgo.com/lite?q=...
    Parses HTML results. No authentication needed.
    """

    ENDPOINT = "https://lite.duckduckgo.com/lite/"

    _LINK_RE = re.compile(
        r'<a[^>]+href=["\'](https?://[^"\']+)["\'][^>]*class=["\'][^"\']*result-link[^"\']*["\'][^>]*>([^<]+)</a>',
        re.IGNORECASE,
    )
    _SNIPPET_RE = re.compile(
        r'<td[^>]*class=["\'][^"\']*result-snippet[^"\']*["\'][^>]*>(.*?)</td>',
        re.DOTALL | re.IGNORECASE,
    )
    _LINK_FALLBACK = re.compile(
        r'<a[^>]+rel=["\']nofollow["\'][^>]+href=["\'](https?://[^"\']+)["\']',
        re.IGNORECASE,
    )

    def __init__(self):
        cfg = SearchApiConfig(provider="duckduckgo", enabled=True, configured=True)
        super().__init__(cfg)

    @property
    def available(self) -> bool:
        return True  # Always available, no key needed

    def search(self, query: str, limit: int = 20) -> List[SearchApiResult]:
        """Search DuckDuckGo Lite. Returns empty list on any error."""
        params = urllib.parse.urlencode({"q": query})
        url = f"{self.ENDPOINT}?{params}"
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            })
            resp = urllib.request.urlopen(req, timeout=15)
            html = resp.read().decode("utf-8", errors="replace")
            self.last_status = resp.status
            self.quota.record_call(success=True)
            return self._parse_html(html, query, limit)
        except Exception as e:
            self.last_error = sanitize_error(e)
            self.quota.record_call(success=False)
            return []

    def _parse_html(self, html: str, query: str, limit: int) -> List[SearchApiResult]:
        # DDG Lite uses result-link anchors with uddg= encoded URLs
        # Pattern: <a rel="nofollow" href="//duckduckgo.com/l/?uddg=ENCODED_URL" class='result-link'>Title</a>
        results = []
        rank = 0
        # Find all result-link anchors
        for m in re.finditer(
            r'<a[^>]*class=["\']result-link["\'][^>]*href=["\']//duckduckgo\.com/l/\?uddg=([^"&\']+)["\'][^>]*>([^<]+)</a>',
            html, re.IGNORECASE
        ):
            if rank >= limit:
                break
            encoded_url = m.group(1)
            title = m.group(2).strip()
            # URL decode the uddg param
            url = urllib.parse.unquote(encoded_url)
            if url and not url.startswith("//"):
                rank += 1
                results.append(SearchApiResult(
                    url=url,
                    title=title,
                    snippet="",
                    source_domain=_extract_domain(url),
                    query=query,
                    rank=rank,
                    raw_data={"engine": "duckduckgo"},
                ))
        return results


class BingSearchClient(BaseSearchClient):
    """Bing Web Search API v7 client. Requires BING_SEARCH_API_KEY in env/.env."""
    ENDPOINT = "https://api.bing.microsoft.com/v7.0/search"

    def __init__(self, config: SearchApiConfig = None, quota: SearchApiQuota = None):
        cfg = config or get_search_api_config("bing")
        super().__init__(cfg, quota)
        if not self.config.endpoint:
            self.config.endpoint = self.ENDPOINT

    @property
    def available(self) -> bool:
        return self.config.enabled and self.config.configured and self.quota.check()

    def search(self, query: str, limit: int = 20) -> List[SearchApiResult]:
        if not self.config.enabled or not self.config.configured:
            self.last_error = "Bing API not configured"
            return []
        if not self.quota.check():
            self.last_error = self.quota.last_error or "quota exhausted"
            return []

        params = {"q": query, "count": min(limit, 50), "mkt": "zh-CN", "responseFilter": "Webpages"}
        url = f"{self.config.endpoint}?{urllib.parse.urlencode(params)}"
        headers = safe_headers(self.config.api_key, "Ocp-Apim-Subscription-Key")
        try:
            req = urllib.request.Request(url, headers=headers)
            resp = urllib.request.urlopen(req, timeout=10)
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
            self.last_status = resp.status
            self.quota.record_call(success=True)
            pages = data.get("webPages", {}).get("value", [])
            results = []
            for i, page in enumerate(pages[:limit]):
                url = page.get("url", "")
                if not url:
                    continue
                results.append(SearchApiResult(
                    url=url,
                    title=page.get("name", ""),
                    snippet=page.get("snippet", ""),
                    source_domain=_extract_domain(url),
                    query=query,
                    rank=i + 1,
                ))
            return results
        except Exception as e:
            self.last_error = sanitize_error(e)
            self.quota.record_call(success=False)
            return []


class NoopSearchClient(BaseSearchClient):
    def search(self, query: str, limit: int = 20) -> List[SearchApiResult]:
        self.last_error = "No search API configured. Start SearXNG or set BING_SEARCH_API_KEY."
        return []
    @property
    def available(self):
        return False


def _extract_domain(url: str) -> str:
    from urllib.parse import urlparse
    return urlparse(url).netloc.lower()


def create_search_client(provider: str = "auto") -> BaseSearchClient:
    """Factory: return best available search client."""
    import os

    if provider == "mock":
        # Import here to avoid circular
        class MockWrapper:
            def __init__(self):
                from .search_api_provider import MockSearchApiProvider
                self._api = MockSearchApiProvider()
            def search(self, q, limit=20):
                return self._api.search(q, limit)
            @property
            def available(self):
                return True
        return MockWrapper()

    if provider == "none":
        return NoopSearchClient(SearchApiConfig(provider="none"))

    if provider == "duckduckgo":
        return DuckDuckGoDirectClient()

    if provider == "searxng":
        client = SearXNGSelfHostClient()
        if client.available:
            return client
        # Fall through to next option

    if provider == "auto":
        # Priority: SearXNG (local) > DuckDuckGo (always works)
        searx = SearXNGSelfHostClient()
        if searx.available:
            return searx
        return DuckDuckGoDirectClient()

    if provider == "bing":
        cfg = get_search_api_config("bing")
        if cfg.configured:
            return BingSearchClient(cfg)
        return NoopSearchClient(cfg)

    return NoopSearchClient(SearchApiConfig(provider=provider))
