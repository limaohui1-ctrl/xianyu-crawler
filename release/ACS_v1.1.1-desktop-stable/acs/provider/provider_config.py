"""
Provider config — loads AI provider settings from environment variables.

Configuration priority:
  1. Environment variables (os.environ)
  2. .env file in working directory
  3. Hard-coded defaults

SECURITY: Never hard-code API keys.  This module reads from env only.

Usage:
    from acs.provider.provider_config import ProviderConfig

    config = ProviderConfig.from_env()
    print(config.base_url, config.model)
"""

from dataclasses import dataclass, field
from typing import Optional
import os


@dataclass
class ProviderConfig:
    """AI provider configuration loaded from environment variables.

    All sensitive fields (api_key) are excluded from repr and safe log output.
    """

    # ── Connection ──
    provider: str = "openai_compatible"
    base_url: str = ""
    api_key: str = field(default="", repr=False)
    model: str = ""

    # ── Request limits ──
    timeout: int = 30
    max_retries: int = 2
    max_tokens: int = 2000
    temperature: float = 0.0

    # ── Cost / safety ──
    ai_parser_enabled: bool = False
    max_calls_per_run: int = 50
    max_calls_per_url: int = 1
    max_cost_per_run: float = 1.00
    log_prompts: bool = False

    @classmethod
    def from_env(cls) -> "ProviderConfig":
        """Load configuration from environment variables.

        Reads the following env vars (all optional):
          AI_PROVIDER, AI_BASE_URL, AI_API_KEY, AI_MODEL,
          AI_TIMEOUT, AI_MAX_RETRIES, AI_MAX_TOKENS, AI_TEMPERATURE,
          AI_PARSER_ENABLED, AI_MAX_CALLS_PER_RUN, AI_MAX_CALLS_PER_URL,
          AI_MAX_COST_PER_RUN, AI_LOG_PROMPTS
        """
        return cls(
            provider=os.getenv("AI_PROVIDER", "openai_compatible"),
            base_url=os.getenv("AI_BASE_URL", ""),
            api_key=os.getenv("AI_API_KEY", ""),
            model=os.getenv("AI_MODEL", ""),
            timeout=int(os.getenv("AI_TIMEOUT", "30")),
            max_retries=int(os.getenv("AI_MAX_RETRIES", "2")),
            max_tokens=int(os.getenv("AI_MAX_TOKENS", "2000")),
            temperature=float(os.getenv("AI_TEMPERATURE", "0.0")),
            ai_parser_enabled=os.getenv("AI_PARSER_ENABLED", "false").lower() in ("true", "1", "yes"),
            max_calls_per_run=int(os.getenv("AI_MAX_CALLS_PER_RUN", "50")),
            max_calls_per_url=int(os.getenv("AI_MAX_CALLS_PER_URL", "1")),
            max_cost_per_run=float(os.getenv("AI_MAX_COST_PER_RUN", "1.00")),
            log_prompts=os.getenv("AI_LOG_PROMPTS", "false").lower() in ("true", "1", "yes"),
        )

    def is_configured(self) -> bool:
        """Check if enough configuration exists to make real API calls."""
        return bool(self.base_url and self.api_key and self.model)

    def safe_repr(self) -> dict:
        """Return a dict safe for logging (no API key)."""
        return {
            "provider": self.provider,
            "base_url": self.base_url,
            "api_key": "***" if self.api_key else "<not set>",
            "model": self.model,
            "timeout": self.timeout,
            "max_retries": self.max_retries,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "ai_parser_enabled": self.ai_parser_enabled,
            "max_calls_per_run": self.max_calls_per_run,
            "max_calls_per_url": self.max_calls_per_url,
            "max_cost_per_run": self.max_cost_per_run,
            "log_prompts": self.log_prompts,
        }

    def to_env_example(self) -> str:
        """Generate a .env.example template."""
        return """
# AI Provider Configuration
# Copy this to .env and fill in your values.
# DO NOT commit .env with real API keys!

AI_PROVIDER=openai_compatible
AI_BASE_URL=https://api.openai.com/v1
AI_API_KEY=sk-your-key-here
AI_MODEL=gpt-4o-mini
AI_TIMEOUT=30
AI_MAX_RETRIES=2
AI_MAX_TOKENS=2000
AI_TEMPERATURE=0.0

# AI Parser safety
AI_PARSER_ENABLED=false
AI_MAX_CALLS_PER_RUN=50
AI_MAX_CALLS_PER_URL=1
AI_MAX_COST_PER_RUN=1.00
AI_LOG_PROMPTS=false
""".strip()
