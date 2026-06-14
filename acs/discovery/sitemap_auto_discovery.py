"""SitemapAutoDiscovery — probe common sitemap paths, read robots sitemaps, parse sitemap XML."""
from typing import List, Optional
from xml.etree import ElementTree as ET
from urllib.parse import urljoin

from .candidate_url import CandidateUrl


COMMON_SITEMAP_PATHS = [
    "/sitemap.xml",
    "/sitemap_index.xml",
    "/sitemap-news.xml",
    "/sitemap1.xml",
    "/sitemap/sitemap.xml",
    "/sitemaps/sitemap.xml",
    "/sitemap_index.xml.gz",
]

SITEMAP_NS = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}


class SitemapAutoDiscovery:
    """Auto-discover sitemaps from common paths + robots.txt extracted URLs."""

    def __init__(self, domain: str, root_url: str, fetch_func=None):
        self.domain = domain
        self.root_url = root_url.rstrip("/")
        self._fetch = fetch_func or self._default_fetch
        self.found_sitemaps: List[str] = []
        self.url_candidates: List[dict] = []

    @staticmethod
    def _default_fetch(url: str) -> tuple:
        import urllib.request
        try:
            req = urllib.request.Request(url, method="GET")
            resp = urllib.request.urlopen(req, timeout=10)
            return resp.read().decode("utf-8", errors="replace"), resp.status
        except Exception as e:
            return None, str(e)

    def probe_common_paths(self) -> "SitemapAutoDiscovery":
        """Probe common sitemap paths for this domain."""
        for path in COMMON_SITEMAP_PATHS:
            url = self.root_url + path
            content, status = self._fetch(url)
            if content and isinstance(status, int) and 200 <= status < 300:
                self.found_sitemaps.append(url)
        return self

    def add_from_robots(self, sitemap_urls: List[str]):
        """Add sitemaps discovered via robots.txt."""
        for u in sitemap_urls:
            if u not in self.found_sitemaps:
                self.found_sitemaps.append(u)

    def parse_sitemaps(self, limit: int = 200) -> List[dict]:
        """Parse all found sitemaps and return CandidateUrl dicts."""
        seen = {}
        for sm_url in self.found_sitemaps:
            if len(seen) >= limit:
                break
            content, status = self._fetch(sm_url)
            if not content:
                continue
            try:
                root = ET.fromstring(content)
            except ET.ParseError:
                continue

            # Sitemap index?
            sitemap_tags = root.findall(".//sitemap") or root.findall(".//s:sitemap", SITEMAP_NS)
            if sitemap_tags:
                # Parse nested sitemaps (limited depth)
                for sm in sitemap_tags:
                    loc = (sm.find("loc") or sm.find("s:loc", SITEMAP_NS))
                    if loc is not None and loc.text:
                        sub_url = urljoin(sm_url, loc.text.strip())
                        if sub_url not in self.found_sitemaps and len(self.found_sitemaps) < 10:
                            sub_content, _ = self._fetch(sub_url)
                            if sub_content:
                                try:
                                    sub_root = ET.fromstring(sub_content)
                                    self._extract_urls(sub_root, seen, limit, sm_url="sitemap_index")
                                except ET.ParseError:
                                    pass
                continue

            # Regular urlset
            self._extract_urls(root, seen, limit, sm_url)

        return list(seen.values())

    def _extract_urls(self, root, seen: dict, limit: int, sm_url: str):
        urls = root.findall(".//url") or root.findall(".//s:url", SITEMAP_NS)
        for u in urls:
            if len(seen) >= limit:
                break
            loc = (u.find("loc") or u.find("s:loc", SITEMAP_NS))
            if loc is not None and loc.text:
                url = loc.text.strip()
                norm = url.lower()
                if norm not in seen:
                    c = CandidateUrl(
                        url=url,
                        title="",
                        snippet=f"Discovered via sitemap: {sm_url}",
                        source_domain=self.domain,
                        source_type="webpage",
                        discovery_method="sitemap_auto",
                        matched_keywords=[],
                        estimated_relevance=0.7,
                        compliance_status="allowed",
                        risk_level="low",
                        reason="sitemap auto-discovery",
                    )
                    seen[norm] = c.to_dict()
