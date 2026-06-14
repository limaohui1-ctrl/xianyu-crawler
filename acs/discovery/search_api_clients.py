"""SearchApiClients — pluggable real search API clients.

Supported: Bing Web Search API (v7).
Pluggable: Google CSE, SerpAPI, Brave Search — add new subclasses.

API keys are read from SearchApiConfig only (env/.env).
No key is ever hardcoded, logged, or included in error output.
"""
import json
import time
import urllib.request
import urllib.error
from abc import ABC, abstractmethod
from typing import List, Optional
from urllib.parse import urlencode

from .search_api_config import SearchApiConfig, get_search_api_config
from .search_api_provider import SearchApiResult
from .search_api_secret_guard import safe_headers, sanitize_error, redact_headers
from .search_api_quota import SearchApiQuota


class BaseSearchClient(ABC):
    """Abstract base for a real search API client."""

    def __init__(self, config: SearchApiConfig, quota: SearchApiQuota = None):
        self.config = config
        self.quota = quota or SearchApiQuota()
        self.last_status = 0
        self.last_error = ""

    @abstractmethod
    def search(self, query: str, limit: int = 20) -> List[SearchApiResult]:
        ...

    @property
    def available(self) -> bool:
        return self.config.enabled and self.quota.check()


class BingSearchClient(BaseSearchClient):
    """Bing Web Search API v7 client.

    Requires: BING_SEARCH_API_KEY in env/.env
    Endpoint: https://api.bing.microsoft.com/v7.0/search
    """

    ENDPOINT = "https://api.bing.microsoft.com/v7.0/search"

    def __init__(self, config: SearchApiConfig = None, quota: SearchApiQuota = None):
        cfg = config or get_search_api_config("bing")
        super().__init__(cfg, quota)
        if not self.config.endpoint:
            self.config.endpoint = self.ENDPOINT

    def search(self, query: str, limit: int = 20) -> List[SearchApiResult]:
        """Call Bing Web Search API. Returns empty list on any error."""
        if not self.config.enabled:
            self.last_error = "Bing API not configured"
            return []

        if not self.quota.check():
            self.last_error = self.quota.last_error or "quota exhausted"
            return []

        params = {"q": query, "count": min(limit, 50), "mkt": "zh-CN", "responseFilter": "Webpages"}
        url = f"{self.config.endpoint}?{urlencode(params)}"
        headers = safe_headers(self.config.api_key, "Ocp-Apim-Subscription-Key")

        try:
            req = urllib.request.Request(url, headers=headers)
            resp = urllib.request.urlopen(req, timeout=10)
            self.last_status = resp.status
            body = resp.read().decode("utf-8", errors="replace")
            data = json.loads(body)
            self.quota.record_call(success=True)
            return self._parse_bing_response(data, query, limit)

        except urllib.error.HTTPError as e:
            self.last_status = e.code
            self.last_error = sanitize_error(e)
            self.quota.record_call(success=False)
            return []

        except Exception as e:
            self.last_status = 0
            self.last_error = sanitize_error(e)
            self.quota.record_call(success=False)
            return []

    def _parse_bing_response(self, data: dict, query: str, limit: int) -> List[SearchApiResult]:
        """Parse Bing v7 JSON response."""
        results = []
        pages = data.get("webPages", {}).get("value", [])
        for i, page in enumerate(pages[:limit]):
            url = page.get("url", "")
            if not url:
                continue
            r = SearchApiResult(
                url=url,
                title=page.get("name", ""),
                snippet=page.get("snippet", ""),
                source_domain=_extract_domain(url),
                query=query,
                rank=i + 1,
            )
            results.append(r)
        return results


class NoopSearchClient(BaseSearchClient):
    """No-op client — used when no real API is configured. Always returns empty."""

    def search(self, query: str, limit: int = 20) -> List[SearchApiResult]:
        self.last_error = "No search API configured. Set BING_SEARCH_API_KEY in .env"
        return []

    @property
    def available(self):
        return False


def _extract_domain(url: str) -> str:
    from urllib.parse import urlparse
    return urlparse(url).netloc.lower()


def create_search_client(provider: str = "auto") -> BaseSearchClient:
    """Factory: return the appropriate search client based on config.

    provider:
      'auto' — detect from ACS_SEARCH_API_PROVIDER env or fallback to bing config check
      'bing' — force Bing
      'google' — force Google (not yet implemented)
      'mock' — MockSearchApiProvider
      'none' — NoopSearchClient
    """
    import os

    if provider == "mock":
        from .topic_discovery_flow import MockSearchApiProvider
        return MockSearchApiProvider()  # duck-typed — has .search()

    if provider == "none":
        return NoopSearchClient(SearchApiConfig(provider="none"))

    # Auto-detect or specific
    if provider == "auto":
        provider = os.environ.get("ACS_SEARCH_API_PROVIDER", "bing")

    cfg = get_search_api_config(provider)
    if not cfg.enabled:
        return NoopSearchClient(cfg)

    if provider == "bing":
        quota = SearchApiQuota(
            daily_limit=int(os.environ.get("ACS_SEARCH_API_DAILY_LIMIT", "100")),
        )
        return BingSearchClient(cfg, quota)

    # Future: google, serpapi, brave...
    return NoopSearchClient(SearchApiConfig(provider=provider,
        message=f"Provider '{provider}' not yet implemented."))
