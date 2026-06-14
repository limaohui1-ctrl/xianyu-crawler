"""DiscoveryConfig — configuration for discovery providers."""
from dataclasses import dataclass, field
from typing import List, Optional
import os


@dataclass
class DiscoveryConfig:
    """Central config for all discovery providers."""

    # General
    default_limit: int = 50
    max_limit: int = 200
    request_timeout: int = 15
    rate_limit_seconds: float = 1.0

    # Sitemap
    sitemap_max_urls: int = 200
    sitemap_allowed_extensions: List[str] = field(default_factory=lambda: [
        ".html", ".htm", ".php", ".asp", ".aspx", "/", ""
    ])

    # RSS
    rss_max_entries: int = 100

    # Import
    import_max_rows: int = 500

    # Compliance domains (will be merged from ComplianceFilter)
    blocked_domains: List[str] = field(default_factory=list)

    def from_env(self) -> "DiscoveryConfig":
        """Load overrides from environment variables."""
        for key in ["default_limit", "max_limit", "request_timeout", "sitemap_max_urls",
                     "rss_max_entries", "import_max_rows"]:
            env_key = f"DISCOVERY_{key.upper()}"
            val = os.environ.get(env_key)
            if val:
                try:
                    setattr(self, key, int(val))
                except ValueError:
                    pass
        rate = os.environ.get("DISCOVERY_RATE_LIMIT")
        if rate:
            try:
                self.rate_limit_seconds = float(rate)
            except ValueError:
                pass
        return self


# Global singleton
_default_config: Optional[DiscoveryConfig] = None


def get_config() -> DiscoveryConfig:
    global _default_config
    if _default_config is None:
        _default_config = DiscoveryConfig().from_env()
    return _default_config
