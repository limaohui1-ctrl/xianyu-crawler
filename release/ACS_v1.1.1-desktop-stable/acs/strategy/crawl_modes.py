"""
Crawl mode definitions — the strategy modes the engine can select.

Six modes, each controlling fetch behavior, parser selection,
retry policy, and rate limiting aggressiveness.

Usage:
    from acs.strategy.crawl_modes import CrawlMode, MODE_DEFAULTS
    config = MODE_DEFAULTS[CrawlMode.FAST]
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class CrawlMode(str, Enum):
    """Available crawl strategy modes."""
    FAST = "fast"                   # Quick extraction, core fields only
    FULL = "full"                   # Complete extraction, all fields
    CONSERVATIVE = "conservative"    # Slow, low frequency, avoids errors
    RETRY_FAILED = "retry_failed"   # Only re-process previously failed URLs
    SHADOW_COMPARE = "shadow_compare"  # Run ACS alongside legacy, compare output
    DEGRADED = "degraded"           # Reduced operations due to errors/cost limits

    # Reserved for future phases — do NOT implement now:
    # AI_RECOVERY = "ai_recovery"   # Phase 4: AI-driven field repair


@dataclass
class ModeConfig:
    """Per-mode behavior configuration."""

    mode: CrawlMode = CrawlMode.FULL

    # ── Fetch ──
    request_delay_seconds: float = 1.0       # Base delay between requests
    max_concurrent_requests: int = 1          # 1 = sequential only
    timeout_seconds: int = 30

    # ── Retry ──
    max_retries: int = 3
    retry_backoff_base: float = 1.5           # base seconds for exponential backoff
    retry_on_4xx: bool = False                # Retry on 4xx (except 429)?
    jitter_enabled: bool = True

    # ── Rate limiting ──
    requests_per_second: float = 2.0          # Global
    requests_per_domain_per_second: float = 1.0
    burst_size: int = 3

    # ── Parsing ──
    prefer_parser: Optional[str] = None       # Force a specific parser (None = auto)
    extract_images: bool = True
    extract_links: bool = True
    extract_tables: bool = True
    max_body_length: int = 20000

    # ── Quality ──
    min_completeness_pct: int = 0             # Skip results below this threshold?

    # ── Logging ──
    verbose_logging: bool = False

    def to_dict(self) -> dict:
        return {
            "mode": self.mode.value,
            "request_delay_seconds": self.request_delay_seconds,
            "max_concurrent_requests": self.max_concurrent_requests,
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
            "retry_backoff_base": self.retry_backoff_base,
            "retry_on_4xx": self.retry_on_4xx,
            "jitter_enabled": self.jitter_enabled,
            "requests_per_second": self.requests_per_second,
            "requests_per_domain_per_second": self.requests_per_domain_per_second,
            "burst_size": self.burst_size,
            "prefer_parser": self.prefer_parser,
            "extract_images": self.extract_images,
            "extract_links": self.extract_links,
            "extract_tables": self.extract_tables,
            "max_body_length": self.max_body_length,
            "min_completeness_pct": self.min_completeness_pct,
            "verbose_logging": self.verbose_logging,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ModeConfig":
        return cls(
            mode=CrawlMode(data.get("mode", "full")),
            request_delay_seconds=float(data.get("request_delay_seconds", 1.0)),
            max_concurrent_requests=int(data.get("max_concurrent_requests", 1)),
            timeout_seconds=int(data.get("timeout_seconds", 30)),
            max_retries=int(data.get("max_retries", 3)),
            retry_backoff_base=float(data.get("retry_backoff_base", 1.5)),
            retry_on_4xx=bool(data.get("retry_on_4xx", False)),
            jitter_enabled=bool(data.get("jitter_enabled", True)),
            requests_per_second=float(data.get("requests_per_second", 2.0)),
            requests_per_domain_per_second=float(data.get("requests_per_domain_per_second", 1.0)),
            burst_size=int(data.get("burst_size", 3)),
            prefer_parser=data.get("prefer_parser"),
            extract_images=bool(data.get("extract_images", True)),
            extract_links=bool(data.get("extract_links", True)),
            extract_tables=bool(data.get("extract_tables", True)),
            max_body_length=int(data.get("max_body_length", 20000)),
            min_completeness_pct=int(data.get("min_completeness_pct", 0)),
            verbose_logging=bool(data.get("verbose_logging", False)),
        )


# ── Mode presets ─────────────────────────────────────────────────

MODE_DEFAULTS: Dict[CrawlMode, ModeConfig] = {
    CrawlMode.FAST: ModeConfig(
        mode=CrawlMode.FAST,
        request_delay_seconds=0.3,
        timeout_seconds=15,
        max_retries=1,
        requests_per_second=5.0,
        extract_images=False,
        extract_links=False,
        extract_tables=False,
        max_body_length=5000,
    ),

    CrawlMode.FULL: ModeConfig(
        mode=CrawlMode.FULL,
        request_delay_seconds=1.0,
        timeout_seconds=30,
        max_retries=3,
        requests_per_second=2.0,
    ),

    CrawlMode.CONSERVATIVE: ModeConfig(
        mode=CrawlMode.CONSERVATIVE,
        request_delay_seconds=5.0,
        timeout_seconds=60,
        max_retries=2,
        retry_on_4xx=False,
        requests_per_second=0.3,
        burst_size=1,
        extract_images=True,
        extract_links=True,
        extract_tables=False,
        verbose_logging=True,
    ),

    CrawlMode.RETRY_FAILED: ModeConfig(
        mode=CrawlMode.RETRY_FAILED,
        request_delay_seconds=2.0,
        timeout_seconds=30,
        max_retries=1,
        requests_per_second=1.0,
    ),

    CrawlMode.SHADOW_COMPARE: ModeConfig(
        mode=CrawlMode.SHADOW_COMPARE,
        request_delay_seconds=1.0,
        timeout_seconds=30,
        max_retries=3,
        verbose_logging=True,
    ),

    CrawlMode.DEGRADED: ModeConfig(
        mode=CrawlMode.DEGRADED,
        request_delay_seconds=10.0,
        timeout_seconds=60,
        max_retries=1,
        retry_on_4xx=False,
        requests_per_second=0.2,
        burst_size=1,
        extract_images=False,
        extract_links=False,
        extract_tables=False,
        max_body_length=2000,
        verbose_logging=True,
    ),
}


def get_mode_config(mode: CrawlMode) -> ModeConfig:
    """Get the default configuration for a crawl mode."""
    return MODE_DEFAULTS.get(mode, MODE_DEFAULTS[CrawlMode.FULL])
