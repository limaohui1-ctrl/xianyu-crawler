"""DomainProfile — aggregate all discovery results for a single domain."""
from typing import List, Optional
from dataclasses import dataclass, field, asdict
from urllib.parse import urlparse

from .domain_input import DomainInput, parse_domain
from .url_normalizer import dedup_urls


@dataclass
class DomainProfile:
    domain: str = ""
    root_url: str = ""
    robots_sitemaps: List[str] = field(default_factory=list)
    robots_disallow_paths: List[str] = field(default_factory=list)
    sitemap_urls_discovered: List[str] = field(default_factory=list)
    feed_urls_discovered: List[str] = field(default_factory=list)
    site_entries: List[dict] = field(default_factory=list)
    sitemap_candidates: List[dict] = field(default_factory=list)
    feed_candidates: List[dict] = field(default_factory=list)
    robots_candidates: List[dict] = field(default_factory=list)
    total_candidates: int = 0
    error: str = ""

    def to_dict(self):
        return asdict(self)


def _apply_robots_disallow(candidates: List[dict], disallow_paths: List[str]):
    """Mark candidates whose URL path matches a robots Disallow rule.

    Matching URLs get compliance_status='blocked' with reason='robots_disallow_path'.
    Does NOT skip — marks explicitly so the user sees the reason.
    """
    if not disallow_paths:
        return
    for c in candidates:
        url = c.get("url", "")
        parsed = urlparse(url)
        path = parsed.path or "/"
        for dp in disallow_paths:
            dp = dp.strip()
            if not dp:
                continue
            # Exact or prefix match
            if path == dp or path.startswith(dp):
                # Blocked — robots explicitly disallows
                c["compliance_status"] = "blocked"
                c["risk_level"] = "high"
                c["reason"] = f"robots Disallow: {dp}"
                c["robots_hint"] = f"Disallow: {dp}"
                break


def _is_commercial_domain(domain: str) -> bool:
    """Check if domain is a known commercial platform. No network call."""
    from .compliance_filter import BLOCKED_DOMAINS
    domain_lower = domain.lower()
    for blocked in BLOCKED_DOMAINS:
        if domain_lower == blocked or domain_lower.endswith("." + blocked):
            return True
    return False


def discover_domain(
    raw_input: str,
    fetch_func=None,
    max_candidates: int = 200,
    enable_robots: bool = True,
    enable_sitemap: bool = True,
    enable_rss: bool = True,
    enable_site_entry: bool = True,
    topic: str = "",
) -> DomainProfile:
    """Run full auto-discovery for a domain.

    This is the main orchestrator for ACS v1.2.0 domain-level discovery.
    Does NOT call real search engines. Does NOT access commercial platforms.

    Safety rules:
    - Commercial platforms are blocked BEFORE any network request.
    - robots.txt Disallow paths mark matching candidates as blocked.
    """
    di = parse_domain(raw_input)
    if not di.is_valid:
        return DomainProfile(domain=di.domain, error=di.reason)

    # ── Commercial domain pre-block ──
    if _is_commercial_domain(di.domain):
        return DomainProfile(
            domain=di.domain,
            root_url=di.root_url,
            error=f"Commercial platform blocked: {di.domain}",
            total_candidates=0,
        )

    profile = DomainProfile(domain=di.domain, root_url=di.root_url)

    # 1. Robots
    if enable_robots:
        from .robots_provider import RobotsProvider
        rp = RobotsProvider(fetch_func=fetch_func)
        rp.fetch(di.root_url)
        profile.robots_sitemaps = rp.sitemap_urls
        profile.robots_disallow_paths = rp.disallow_paths
        profile.robots_candidates = rp.to_candidates(di.domain, topic)

    # 2. Sitemap
    if enable_sitemap:
        from .sitemap_auto_discovery import SitemapAutoDiscovery
        sd = SitemapAutoDiscovery(di.domain, di.root_url, fetch_func=fetch_func)
        sd.probe_common_paths()
        if enable_robots and profile.robots_sitemaps:
            sd.add_from_robots(profile.robots_sitemaps)
        profile.sitemap_urls_discovered = sd.found_sitemaps
        profile.sitemap_candidates = sd.parse_sitemaps(limit=max_candidates)

    # 3. RSS
    if enable_rss:
        from .rss_auto_discovery import RssAutoDiscovery
        rd = RssAutoDiscovery(di.domain, di.root_url, fetch_func=fetch_func)
        rd.probe_common_paths()
        rd.probe_homepage_links()
        profile.feed_urls_discovered = rd.found_feeds
        profile.feed_candidates = rd.parse_feeds(limit=max_candidates)

    # 4. Site entry (only if domain passed commercial pre-block above)
    if enable_site_entry:
        from .site_entry_discovery import SiteEntryDiscovery
        se = SiteEntryDiscovery(di.domain, di.root_url, fetch_func=fetch_func)
        profile.site_entries = se.probe(max_paths=12)

    # 5. Apply robots Disallow rules to all candidates
    if profile.robots_disallow_paths:
        _apply_robots_disallow(profile.sitemap_candidates, profile.robots_disallow_paths)
        _apply_robots_disallow(profile.feed_candidates, profile.robots_disallow_paths)
        _apply_robots_disallow(profile.site_entries, profile.robots_disallow_paths)
        _apply_robots_disallow(profile.robots_candidates, profile.robots_disallow_paths)

    # 6. Merge + dedup
    all_candidates = (
        profile.robots_candidates +
        profile.sitemap_candidates +
        profile.feed_candidates +
        profile.site_entries
    )
    all_candidates = dedup_urls(all_candidates, url_key="url")
    profile.total_candidates = len(all_candidates)

    return profile
