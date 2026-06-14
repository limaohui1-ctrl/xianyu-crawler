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

    SUPPORTED = ["bing", "google", "serpapi"]

    def __init__(self):
        self._clients: Dict[str, BaseSearchClient] = {}

    def get_client(self, provider: str = "auto") -> BaseSearchClient:
        """Get or create a cached client."""
        if provider not in self._clients:
            self._clients[provider] = create_search_client(provider)
        return self._clients[provider]

    @property
    def is_real_configured(self) -> bool:
        """Return True if at least one real search API has a key."""
        for prov in self.SUPPORTED:
            cfg = get_search_api_config(prov)
            if cfg.configured:
                return True
        return False

    @property
    def active_provider(self) -> str:
        """Return the currently active provider name."""
        return os.environ.get("ACS_SEARCH_API_PROVIDER", "bing")

    def status(self) -> dict:
        """Return config status for each supported provider (keys redacted)."""
        result = {"real_configured": self.is_real_configured, "active": self.active_provider, "providers": {}}
        for prov in self.SUPPORTED:
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
