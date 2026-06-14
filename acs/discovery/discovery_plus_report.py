"""DiscoveryPlusReport — summary report for domain-level auto-discovery."""
import time
from dataclasses import dataclass, asdict
from typing import List, Optional


@dataclass
class DiscoveryPlusReport:
    batch_id: str = ""
    domain: str = ""
    root_url: str = ""
    total_candidates: int = 0
    robots_sitemaps_found: int = 0
    sitemaps_found: int = 0
    feeds_found: int = 0
    site_entries_found: int = 0
    dupe_count: int = 0
    created_at: str = ""

    @classmethod
    def from_profile(cls, profile, batch_id: str = "") -> "DiscoveryPlusReport":
        import time as _time
        return cls(
            batch_id=batch_id or f"dp_{profile.domain}_{int(_time.time())}",
            domain=profile.domain,
            root_url=profile.root_url,
            total_candidates=profile.total_candidates,
            robots_sitemaps_found=len(profile.robots_sitemaps),
            sitemaps_found=len(profile.sitemap_urls_discovered),
            feeds_found=len(profile.feed_urls_discovered),
            site_entries_found=len(profile.site_entries),
            dupe_count=0,
            created_at=_time.strftime("%Y-%m-%dT%H:%M:%S"),
        )
