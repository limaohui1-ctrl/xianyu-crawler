"""UrlNormalizer — normalize URLs and deduplicate."""
import re
from collections import OrderedDict
from typing import List
from urllib.parse import urlparse, urlunparse


# Tracking parameters to strip
_TRACKING_PARAMS = re.compile(r"^(utm_\w+|fbclid|gclid|ref|source)$", re.IGNORECASE)


def normalize_url(url: str) -> str:
    """Normalize a URL for deduplication.

    Rules:
    - Remove #fragment
    - Remove tracking params (utm_*, fbclid, gclid)
    - Lowercase domain
    - Normalize trailing slash: keep path-based trailing slash, strip root trailing slash

    Returns normalized URL string.
    """
    if not url:
        return ""
    url = url.strip()
    parsed = urlparse(url)
    # Lowercase netloc
    netloc = parsed.netloc.lower()
    # Remove fragment
    # Rebuild query: strip tracking params
    qs = parsed.query
    if qs:
        params = []
        for pair in qs.split("&"):
            if "=" in pair:
                k, v = pair.split("=", 1)
                if not _TRACKING_PARAMS.match(k):
                    params.append(f"{k}={v}")
            else:
                if not _TRACKING_PARAMS.match(pair):
                    params.append(pair)
        qs = "&".join(params)

    path = parsed.path or "/"
    # Normalize: strip trailing slash except for root "/"
    if path != "/" and path.endswith("/"):
        path = path[:-1]

    normalized = urlunparse((parsed.scheme, netloc, path, parsed.params, qs, ""))
    return normalized


def dedup_urls(candidates: List[dict], url_key: str = "url") -> List[dict]:
    """Deduplicate candidate dicts by normalized URL. First occurrence wins."""
    seen = OrderedDict()
    for c in candidates:
        url = c.get(url_key, "")
        norm = normalize_url(url)
        if norm not in seen:
            c["normalized_url"] = norm
            seen[norm] = c
        else:
            # Mark as duplicate, keep source info
            c["normalized_url"] = norm
            c["is_duplicate"] = True
            c["duplicate_of"] = seen[norm].get(url_key, "")

    result = list(seen.values())
    for r in result:
        r.setdefault("is_duplicate", False)
    return result
