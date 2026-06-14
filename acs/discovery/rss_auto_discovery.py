"""RssAutoDiscovery — auto-discover RSS/Atom feeds from common paths and HTML <link> tags."""
import re
from typing import List, Optional
from xml.etree import ElementTree as ET
from urllib.parse import urljoin

from .candidate_url import CandidateUrl


COMMON_FEED_PATHS = [
    "/rss", "/feed", "/feed.xml", "/atom.xml",
    "/index.xml", "/rss.xml", "/news/rss", "/blog/feed",
]

FEED_LINK_RE = re.compile(
    r'<link[^>]+rel=["\'](?:alternate|feed)["\'][^>]+type=["\']application/(?:rss|atom)\+xml["\'][^>]*href=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
FEED_LINK_RE2 = re.compile(
    r'<link[^>]+href=["\']([^"\']+)["\'][^>]+type=["\']application/(?:rss|atom)\+xml["\']',
    re.IGNORECASE,
)


class RssAutoDiscovery:
    """Auto-discover RSS/Atom feeds from common paths and HTML <link> tags."""

    def __init__(self, domain: str, root_url: str, fetch_func=None):
        self.domain = domain
        self.root_url = root_url.rstrip("/")
        self._fetch = fetch_func or self._default_fetch
        self.found_feeds: List[str] = []
        self.entries: List[dict] = []

    @staticmethod
    def _default_fetch(url: str) -> tuple:
        import urllib.request
        try:
            req = urllib.request.Request(url, method="GET")
            resp = urllib.request.urlopen(req, timeout=10)
            return resp.read().decode("utf-8", errors="replace"), resp.status
        except Exception as e:
            return None, str(e)

    def probe_common_paths(self) -> "RssAutoDiscovery":
        """Probe common feed paths."""
        for path in COMMON_FEED_PATHS:
            url = self.root_url + path
            content, status = self._fetch(url)
            if content and isinstance(status, int) and 200 <= status < 300:
                self.found_feeds.append(url)
        return self

    def probe_homepage_links(self) -> "RssAutoDiscovery":
        """Parse homepage HTML for <link rel="alternate"> feed references."""
        content, _ = self._fetch(self.root_url + "/")
        if not content:
            return self
        for pattern in (FEED_LINK_RE, FEED_LINK_RE2):
            for m in pattern.finditer(content):
                href = m.group(1)
                feed_url = urljoin(self.root_url, href)
                if feed_url not in self.found_feeds:
                    self.found_feeds.append(feed_url)
        return self

    def parse_feeds(self, limit: int = 100) -> List[dict]:
        """Parse all found feeds into CandidateUrl entries."""
        seen = {}
        for feed_url in self.found_feeds:
            if len(seen) >= limit:
                break
            content, _ = self._fetch(feed_url)
            if not content:
                continue
            try:
                root = ET.fromstring(content)
            except ET.ParseError:
                continue

            # RSS 2.0
            items = root.findall(".//item")
            for item in items:
                if len(seen) >= limit:
                    break
                link = item.find("link")
                title = item.find("title")
                desc = item.find("description")
                url = link.text.strip() if link is not None and link.text else ""
                if url and url.lower() not in seen:
                    c = CandidateUrl(
                        url=url,
                        title=title.text.strip() if title is not None and title.text else "",
                        snippet=(desc.text or "")[:200] if desc is not None and desc.text else "",
                        source_domain=self.domain,
                        source_type="webpage",
                        discovery_method="rss_auto",
                        matched_keywords=[],
                        estimated_relevance=0.6,
                        compliance_status="allowed",
                        risk_level="low",
                        reason="RSS auto-discovery",
                    )
                    seen[url.lower()] = c.to_dict()

            # Atom
            entries = root.findall(".//{http://www.w3.org/2005/Atom}entry")
            for entry in entries:
                if len(seen) >= limit:
                    break
                link_el = entry.find("{http://www.w3.org/2005/Atom}link")
                title_el = entry.find("{http://www.w3.org/2005/Atom}title")
                summary_el = entry.find("{http://www.w3.org/2005/Atom}summary")
                href = link_el.get("href", "") if link_el is not None else ""
                if href and href.lower() not in seen:
                    c = CandidateUrl(
                        url=href,
                        title=title_el.text.strip() if title_el is not None and title_el.text else "",
                        snippet=(summary_el.text or "")[:200] if summary_el is not None and summary_el.text else "",
                        source_domain=self.domain,
                        source_type="webpage",
                        discovery_method="rss_auto",
                        matched_keywords=[],
                        estimated_relevance=0.6,
                        compliance_status="allowed",
                        risk_level="low",
                        reason="RSS auto-discovery",
                    )
                    seen[href.lower()] = c.to_dict()

        return list(seen.values())
