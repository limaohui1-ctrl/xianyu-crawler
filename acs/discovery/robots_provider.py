"""RobotsProvider — fetch and parse robots.txt for sitemap URLs and disallow rules."""
import re
from typing import List, Optional
from urllib.parse import urljoin

from .candidate_url import CandidateUrl


class RobotsProvider:
    """Read and parse a public robots.txt. Extracts Sitemap links and Disallow rules."""

    SITEMAP_RE = re.compile(r"^\s*Sitemap:\s*(\S+)", re.IGNORECASE)
    DISALLOW_RE = re.compile(r"^\s*Disallow:\s*(\S+)", re.IGNORECASE)
    ALLOW_RE = re.compile(r"^\s*Allow:\s*(\S+)", re.IGNORECASE)

    def __init__(self, fetch_func=None):
        """fetch_func(url) -> (content_str, status_code) or (None, error_code)"""
        self._fetch = fetch_func or self._default_fetch
        self.sitemap_urls: List[str] = []
        self.disallow_paths: List[str] = []
        self.allow_paths: List[str] = []
        self.fetch_success = False
        self.status_code = 0
        self.error = ""

    @staticmethod
    def _default_fetch(url: str) -> tuple:
        """Default fetch using urllib — mocked in tests."""
        import urllib.request
        try:
            req = urllib.request.Request(url, method="GET")
            resp = urllib.request.urlopen(req, timeout=10)
            return resp.read().decode("utf-8", errors="replace"), resp.status
        except Exception as e:
            return None, str(e)

    def fetch(self, root_url: str) -> "RobotsProvider":
        """Fetch and parse robots.txt from root_url."""
        url = root_url.rstrip("/") + "/robots.txt"
        content, status = self._fetch(url)

        if content is None:
            self.error = str(status)
            self.status_code = 0
            return self

        self.fetch_success = True
        self.status_code = status if isinstance(status, int) else 0

        for line in content.splitlines():
            line = line.strip()
            # Sitemap
            m = self.SITEMAP_RE.match(line)
            if m:
                sitemap = m.group(1).strip()
                # Resolve relative
                sitemap = urljoin(url, sitemap)
                self.sitemap_urls.append(sitemap)
                continue
            # Disallow (for reference only — never overrides compliance)
            m = self.DISALLOW_RE.match(line)
            if m:
                path = m.group(1).strip()
                if path:
                    self.disallow_paths.append(path)
                continue
            m = self.ALLOW_RE.match(line)
            if m:
                path = m.group(1).strip()
                if path:
                    self.allow_paths.append(path)

        return self

    def to_candidates(self, domain: str, topic: str = "") -> List[dict]:
        """Convert extracted sitemap URLs to CandidateUrl dicts."""
        candidates = []
        for s in self.sitemap_urls:
            c = CandidateUrl(
                url=s,
                title=f"Sitemap of {domain}",
                snippet=f"Discovered from robots.txt on {domain}",
                source_domain=domain,
                source_type="sitemap_index",
                discovery_method="robots_sitemap",
                matched_keywords=[],
                estimated_relevance=0.9,
                compliance_status="allowed",
                risk_level="low",
                reason="robots.txt sitemap reference",
            )
            candidates.append(c.to_dict())
        return candidates
