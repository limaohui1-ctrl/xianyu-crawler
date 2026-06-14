"""RSS Provider — parse RSS/Atom feeds to discover candidate URLs."""
import re
import time
from typing import List
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

from .candidate_url import CandidateUrl
from .discovery_config import get_config


class RssProvider:
    """Parse RSS 2.0 and Atom feeds to extract URL candidates.

    Compliant: only reads public feeds. Never bypasses access controls.
    """

    def __init__(self):
        self.config = get_config()

    def discover(self, feed_url: str, topic: str = "",
                 keywords: List[str] = None,
                 max_entries: int = 0) -> List[CandidateUrl]:
        """Fetch and parse an RSS/Atom feed.

        Args:
            feed_url: Full URL to RSS/Atom feed
            topic: Topic for relevance context
            keywords: Keywords for matching
            max_entries: Max entries (0 = config default)

        Returns:
            List of CandidateUrl objects (one per feed entry)
        """
        if not max_entries:
            max_entries = self.config.rss_max_entries

        try:
            import urllib.request
            req = urllib.request.Request(feed_url, headers={
                "User-Agent": "ACS-RSS-Discovery/1.0 (compliant; public feeds only)",
            })
            resp = urllib.request.urlopen(req, timeout=self.config.request_timeout)
            xml_text = resp.read()
        except Exception:
            return []

        time.sleep(self.config.rate_limit_seconds)

        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return []

        tag = self._tag(root)

        if tag == "rss":
            return self._parse_rss(root, topic, keywords or [], max_entries)
        elif tag == "feed":
            return self._parse_atom(root, topic, keywords or [], max_entries)
        else:
            return []

    def _parse_rss(self, root, topic: str, keywords: List[str],
                   max_entries: int) -> List[CandidateUrl]:
        candidates = []
        channel = root.find("channel")
        if channel is None:
            return candidates

        items = channel.findall("item")
        for item in items[:max_entries]:
            c = self._entry_to_candidate_rss(item, keywords)
            if c:
                candidates.append(c)
        return candidates

    def _parse_atom(self, root, topic: str, keywords: List[str],
                    max_entries: int) -> List[CandidateUrl]:
        candidates = []
        entries = root.findall("{http://www.w3.org/2005/Atom}entry")
        if not entries:
            entries = root.findall("entry")

        for entry in entries[:max_entries]:
            c = self._entry_to_candidate_atom(entry, keywords)
            if c:
                candidates.append(c)
        return candidates

    def _entry_to_candidate_rss(self, item, keywords: List[str]) -> CandidateUrl:
        """Extract CandidateUrl from an RSS <item>."""
        url = ""
        title = ""
        snippet = ""

        for child in item:
            name = self._tag(child)
            if name == "link" and not url:
                url = (child.text or "").strip()
            elif name == "guid" and not url:
                val = (child.text or "").strip()
                if val.startswith(("http://", "https://")):
                    url = val
            elif name == "title":
                title = (child.text or "").strip()
            elif name == "description":
                snippet = self._strip_html(child.text or "")

        # Some RSS feeds have <link> as attribute
        if not url:
            for child in item:
                if self._tag(child) == "link" and not url:
                    url = (child.text or "").strip()
            # Check attributes
            for child in item:
                href = child.get("href", "")
                if href.startswith(("http://", "https://")) and not url:
                    url = href

        if not url or not url.startswith(("http://", "https://")):
            return None

        domain = urlparse(url).netloc.replace("www.", "")
        return CandidateUrl(
            url=url, title=title, snippet=snippet,
            source_domain=domain,
            source_type="webpage",
            discovery_method="rss",
            matched_keywords=keywords,
        )

    def _entry_to_candidate_atom(self, entry, keywords: List[str]) -> CandidateUrl:
        """Extract CandidateUrl from an Atom <entry>."""
        ns = "http://www.w3.org/2005/Atom"
        url = ""
        title = ""
        snippet = ""

        for child in entry:
            name = self._tag(child)
            if name == "link":
                href = child.get("href", "")
                rel = child.get("rel", "alternate")
                if not url or rel == "alternate":
                    if href.startswith(("http://", "https://")):
                        url = href
            elif name == "id" and not url:
                val = (child.text or "").strip()
                if val.startswith(("http://", "https://")):
                    url = val
            elif name == "title":
                title = (child.text or "").strip()
            elif name in ("summary", "content"):
                snippet = self._strip_html(child.text or "")

        if not url:
            return None

        domain = urlparse(url).netloc.replace("www.", "")
        return CandidateUrl(
            url=url, title=title, snippet=snippet,
            source_domain=domain,
            source_type="webpage",
            discovery_method="rss",
            matched_keywords=keywords,
        )

    def _strip_html(self, text: str) -> str:
        """Remove HTML tags from text."""
        if not text:
            return ""
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()[:300]

    def _tag(self, elem) -> str:
        return elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
