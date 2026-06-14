"""SearchApiProviderRegistry — manage multiple search API clients.

Provides:
  - Client lookup by provider name
  - Config status for UI
  - Real vs mock detection
"""
import os
from typing import Dict, Optional

from .search_api_config import get_search_api_config
from .search_api_clients import create_search_client, BaseSearchClient
from .search_api_secret_guard import mask_key


class SearchApiRegistry:
    """Registry of available search API clients."""

    SUPPORTED = ["searxng", "duckduckgo", "bing", "google", "serpapi"]

    def __init__(self):
        self._clients: Dict[str, BaseSearchClient] = {}

    def get_client(self, provider: str = "auto") -> BaseSearchClient:
        """Get or create a cached client."""
        if provider not in self._clients:
            self._clients[provider] = create_search_client(provider)
        return self._clients[provider]

    @property
    def is_real_configured(self) -> bool:
        """Return True if at least one real search API is available."""
        # Check SearXNG first (local, no key needed — just reachable)
        if self._check_searxng():
            return True
        # Fall back to checking remote API keys
        for prov in self.SUPPORTED:
            if prov == "searxng" or prov == "duckduckgo":
                continue
            cfg = get_search_api_config(prov)
            if cfg.configured:
                return True
        return False

    @staticmethod
    def _check_searxng() -> bool:
        import urllib.request, json
        try:
            req = urllib.request.Request("http://127.0.0.1:8080/config")
            resp = urllib.request.urlopen(req, timeout=3)
            if resp.status == 200:
                data = json.loads(resp.read().decode())
                engines = data.get("engines", [])
                enabled = [e for e in engines if e.get("enabled")]
                return len(enabled) > 0
        except Exception:
            pass
        return False

    @property
    def active_provider(self) -> str:
        """Return the currently active provider name."""
        env_provider = os.environ.get("ACS_SEARCH_PROVIDER", "")
        if env_provider:
            return env_provider
        # Auto-detect: SearXNG if running, else duckduckgo, else bing
        if self._check_searxng():
            return "searxng"
        from .search_api_clients import DuckDuckGoDirectClient
        if DuckDuckGoDirectClient().available:
            return "duckduckgo"
        return "bing"

    def status(self) -> dict:
        """Return config status for each supported provider (keys redacted)."""
        result = {"real_configured": self.is_real_configured, "active": self.active_provider, "providers": {}}
        for prov in self.SUPPORTED:
            if prov == "searxng":
                # SearXNG status: check health endpoint
                running = False
                try:
                    import urllib.request
                    req = urllib.request.Request("http://127.0.0.1:8080/healthz", method="GET")
                    resp = urllib.request.urlopen(req, timeout=2)
                    running = resp.status == 200
                except Exception:
                    pass
                result["providers"][prov] = {
                    "configured": running,
                    "enabled": running,
                    "masked_key": "[LOCAL]" if running else "[NOT RUNNING]",
                    "message": "SearXNG local — docker compose up -d" if not running else "SearXNG running on 127.0.0.1:8080",
                }
                continue
            cfg = get_search_api_config(prov)
            result["providers"][prov] = {
                "configured": cfg.configured,
                "enabled": cfg.enabled,
                "masked_key": mask_key(cfg.api_key) if cfg.api_key else "[NOT SET]",
                "message": cfg.message or "",
            }
        return result


_registry: Optional[SearchApiRegistry] = None


def get_search_registry() -> SearchApiRegistry:
    """Get the singleton registry."""
    global _registry
    if _registry is None:
        _registry = SearchApiRegistry()
    return _registry
