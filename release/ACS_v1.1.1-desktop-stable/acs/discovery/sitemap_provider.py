"""Sitemap Provider — parse sitemap.xml to discover candidate URLs."""
import re
import time
from typing import List
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

from .candidate_url import CandidateUrl
from .discovery_config import get_config


class SitemapProvider:
    """Parse sitemap XML (and sitemap index) to extract URL candidates.

    Compliant: only reads public sitemaps. Never bypasses access controls.
    """

    NAMESPACES = {
        "sm": "http://www.sitemaps.org/schemas/sitemap/0.9",
        "": "http://www.sitemaps.org/schemas/sitemap/0.9",
    }

    def __init__(self):
        self.config = get_config()
        self._seen = set()

    def discover(self, sitemap_url: str, topic: str = "",
                 keywords: List[str] = None,
                 max_urls: int = 0) -> List[CandidateUrl]:
        """Fetch and parse a sitemap (or sitemap index).

        Args:
            sitemap_url: Full URL to sitemap.xml
            topic: Topic for relevance context
            keywords: Keywords for matching
            max_urls: Max URLs to return (0 = use config default)

        Returns:
            List of CandidateUrl objects
        """
        if not max_urls:
            max_urls = self.config.sitemap_max_urls

        self._seen = set()
        candidates = []
        self._parse_sitemap(sitemap_url, candidates, max_urls)

        # Assign keywords and topic context
        kw = keywords or []
        for c in candidates:
            c.matched_keywords = kw
            c.source_type = "webpage"
            c.discovery_method = "sitemap"

        return candidates[:max_urls]

    def _parse_sitemap(self, url: str, candidates: list, max_urls: int):
        """Recursively parse sitemap or sitemap index."""
        if len(candidates) >= max_urls:
            return
        if url in self._seen:
            return
        self._seen.add(url)

        try:
            import urllib.request
            req = urllib.request.Request(url, headers={
                "User-Agent": "ACS-Sitemap-Discovery/1.0 (compliant; public sitemaps only)",
            })
            resp = urllib.request.urlopen(req, timeout=self.config.request_timeout)
            xml_text = resp.read()
        except Exception:
            return

        time.sleep(self.config.rate_limit_seconds)

        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return

        # Detect if this is a sitemap index or a regular sitemap
        tag = self._tag(root)
        if tag == "sitemapindex":
            for sm_elem in root:
                if self._tag(sm_elem) == "sitemap":
                    loc = self._child_text(sm_elem, "loc")
                    if loc and loc.startswith(("http://", "https://")):
                        self._parse_sitemap(loc, candidates, max_urls)
        elif tag == "urlset":
            for url_elem in root:
                if len(candidates) >= max_urls:
                    break
                if self._tag(url_elem) == "url":
                    loc = self._child_text(url_elem, "loc")
                    if not loc or not loc.startswith(("http://", "https://")):
                        continue
                    # Filter by allowed extensions
                    if not self._is_allowed_url(loc):
                        continue
                    domain = urlparse(loc).netloc.replace("www.", "")
                    candidates.append(CandidateUrl(
                        url=loc,
                        title="",
                        snippet="",
                        source_domain=domain,
                    ))

    def _tag(self, elem) -> str:
        """Get the local tag name ignoring namespace."""
        return elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag

    def _child_text(self, parent, tag) -> str:
        for child in parent:
            if self._tag(child) == tag:
                return (child.text or "").strip()
        return ""

    def _is_allowed_url(self, url: str) -> bool:
        """Filter URLs by config's allowed extensions."""
        if not self.config.sitemap_allowed_extensions:
            return True
        path = urlparse(url).path.lower()
        if not path or path == "/":
            return True
        return any(path.endswith(ext) for ext in self.config.sitemap_allowed_extensions)
