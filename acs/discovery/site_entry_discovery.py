"""SiteEntryDiscovery — probe common public entry points on a domain.

Commercial platforms are pre-blocked BEFORE any network request.
"""
from typing import List, Optional

from .candidate_url import CandidateUrl


COMMON_ENTRY_PATHS = [
    "/news", "/articles", "/posts", "/notice", "/gonggao",
    "/zhengce", "/policy", "/public", "/open", "/data",
    "/download", "/documents", "/reports", "/info", "/announcement",
]


def _is_commercial(domain: str) -> bool:
    """Check if domain is a known commercial platform BEFORE any network call."""
    from .compliance_filter import BLOCKED_DOMAINS
    dl = domain.lower()
    for b in BLOCKED_DOMAINS:
        if dl == b or dl.endswith("." + b):
            return True
    return False


class SiteEntryDiscovery:
    """Probe common public entry points. Commercial domains rejected before fetch."""

    def __init__(self, domain: str, root_url: str, fetch_func=None):
        self.domain = domain
        self.root_url = root_url.rstrip("/")
        self._fetch = fetch_func or self._default_fetch
        self.entries: List[dict] = []
        self.blocked = False
        self.block_reason = ""

    @staticmethod
    def _default_fetch(url: str) -> tuple:
        import urllib.request
        try:
            req = urllib.request.Request(url, method="GET")
            resp = urllib.request.urlopen(req, timeout=8)
            return resp.read().decode("utf-8", errors="replace"), resp.status
        except Exception as e:
            return None, str(e)

    def probe(self, max_paths: int = 15) -> List[dict]:
        """Probe common paths. Returns empty list with block_reason if commercial."""
        if _is_commercial(self.domain):
            self.blocked = True
            self.block_reason = f"Commercial platform blocked: {self.domain}"
            return []

        paths = COMMON_ENTRY_PATHS[:max_paths]
        for path in paths:
            url = self.root_url + path
            content, status = self._fetch(url)
            if content and isinstance(status, int) and 200 <= status < 300:
                c = CandidateUrl(
                    url=url,
                    title=f"{self.domain}{path}",
                    snippet=f"Public entry point on {self.domain}",
                    source_domain=self.domain,
                    source_type="webpage",
                    discovery_method="site_entry",
                    matched_keywords=[],
                    estimated_relevance=0.5,
                    compliance_status="allowed",
                    risk_level="low",
                    reason=f"site entry probe: {path}",
                )
                self.entries.append(c.to_dict())
        return self.entries
