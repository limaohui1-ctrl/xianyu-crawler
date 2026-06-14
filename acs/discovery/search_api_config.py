"""SearchApiConfig — manage search API credentials from environment.

API keys are read ONLY from environment variables or .env file.
Never hardcoded. Never logged. Never in reports.

Supported providers:
  - bing: BING_SEARCH_API_KEY, BING_SEARCH_ENDPOINT
  - google: GOOGLE_API_KEY, GOOGLE_CSE_ID
  - serpapi: SERPAPI_API_KEY
  - none: no search API configured
"""
import os
from dataclasses import dataclass, field, asdict
from typing import Optional


SUPPORTED_PROVIDERS = ["bing", "google", "serpapi", "none"]

ENV_MAP = {
    "bing": {
        "api_key": "BING_SEARCH_API_KEY",
        "endpoint": "BING_SEARCH_ENDPOINT",
        "extra": {},
    },
    "google": {
        "api_key": "GOOGLE_API_KEY",
        "cse_id": "GOOGLE_CSE_ID",
        "extra": {},
    },
    "serpapi": {
        "api_key": "SERPAPI_API_KEY",
        "extra": {},
    },
}


@dataclass
class SearchApiConfig:
    provider: str = "none"        # bing, google, serpapi, none
    api_key: str = ""             # [REDACTED] in reports
    endpoint: str = ""            # API endpoint URL
    enabled: bool = False         # Only True when key is configured
    configured: bool = False      # Has a non-empty API key env var
    message: str = ""             # User-facing status message

    def to_dict(self):
        d = asdict(self)
        if d["api_key"]:
            d["api_key"] = "[REDACTED]"
        return d

    def to_safe_dict(self):
        """Return config for UI — never includes real key."""
        return {
            "provider": self.provider,
            "enabled": self.enabled,
            "configured": self.configured,
            "message": self.message,
        }


def _load_env_file():
    """Try to read project .env file for API keys. Never raises."""
    try:
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))), ".env")
        if not os.path.isfile(path):
            return
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v
    except Exception:
        pass


def get_search_api_config(provider: str = "bing") -> SearchApiConfig:
    """Get search API configuration. Tries env vars, then .env file.

    Returns SearchApiConfig with enabled=True only if a real API key is found.
    Key is never returned in to_dict() or to_safe_dict().
    """
    _load_env_file()

    if provider not in SUPPORTED_PROVIDERS or provider == "none":
        return SearchApiConfig(
            provider=provider,
            message=f"Provider '{provider}' not supported or disabled. "
                     f"Supported: {', '.join(SUPPORTED_PROVIDERS)}",
        )

    mapping = ENV_MAP.get(provider, {})
    api_key = os.environ.get(mapping.get("api_key", ""), "")
    endpoint = os.environ.get(mapping.get("endpoint", ""), "")

    configured = bool(api_key)
    enabled = configured  # Future: could add explicit enable/disable toggle

    msg = ""
    if not configured:
        env_name = mapping.get("api_key", "API_KEY")
        msg = f"搜索 API 未配置。请在 .env 文件中设置 {env_name} 后重新启动。"

    return SearchApiConfig(
        provider=provider,
        api_key=api_key,
        endpoint=endpoint,
        enabled=enabled,
        configured=configured,
        message=msg,
    )
