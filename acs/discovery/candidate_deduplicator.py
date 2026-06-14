"""CandidateDeduplicator — advanced dedup for topic-level discovery.

Dedup by: normalized URL, title similarity, domain+path overlap.
Also limits candidates per domain to prevent single-site flooding.
"""
import re
from typing import List
from urllib.parse import urlparse
from .url_normalizer import normalize_url


def _normalize_title(title: str) -> str:
    """Strip whitespace, lower, remove common noise for comparison."""
    t = (title or "").strip().lower()
    t = re.sub(r'[\s\-\|\—\–]+', ' ', t)
    t = re.sub(r'[^\w\s]', '', t)
    return ' '.join(t.split())


def _titles_similar(t1: str, t2: str, threshold: float = 0.85) -> bool:
    """Check if two titles are very similar by word overlap."""
    w1 = set(_normalize_title(t1).split())
    w2 = set(_normalize_title(t2).split())
    if not w1 or not w2:
        return False
    intersection = w1 & w2
    union = w1 | w2
    return len(intersection) / len(union) >= threshold


def _domain_path_key(url: str) -> str:
    """Extract domain + first path segment for soft dedup."""
    parsed = urlparse(normalize_url(url))
    path = parsed.path.rstrip('/')
    # Get first meaningful path segment
    parts = [p for p in path.split('/') if p]
    first = parts[0] if parts else ''
    return f"{parsed.netloc}/{first}"


def dedup_candidates(
    candidates: List[dict],
    max_per_domain: int = 10,
    title_similarity_threshold: float = 0.85,
) -> List[dict]:
    """Deduplicate candidates by multiple strategies.

    1. Exact normalized URL dedup (strict)
    2. Title similarity dedup (soft)
    3. Domain+first-path dedup (medium)
    4. Per-domain cap (max_per_domain)

    Returns deduplicated list with is_duplicate flags set.
    """
    seen_norm_urls = set()
    seen_titles = []
    seen_dp_keys = set()
    domain_counts = {}
    result = []

    for c in candidates:
        url = c.get("url", "")
        title = c.get("title", "")
        domain = c.get("source_domain", "") or urlparse(url).netloc

        # 1. Exact norm URL
        norm = normalize_url(url)
        if norm in seen_norm_urls:
            c["is_duplicate"] = True
            c["duplicate_reason"] = "exact_url"
            continue

        # 2. Title similarity
        norm_title = _normalize_title(title)
        is_title_dup = False
        for prev in seen_titles:
            if _titles_similar(norm_title, prev, title_similarity_threshold):
                is_title_dup = True
                c["is_duplicate"] = True
                c["duplicate_reason"] = "similar_title"
                break
        if is_title_dup:
            continue

        # 3. Domain+path soft dedup
        dp_key = _domain_path_key(url)
        if dp_key in seen_dp_keys:
            c["is_duplicate"] = True
            c["duplicate_reason"] = "same_domain_path"
            continue

        # 4. Per-domain cap
        domain_counts[domain] = domain_counts.get(domain, 0) + 1
        if domain_counts[domain] > max_per_domain:
            c["is_duplicate"] = True
            c["duplicate_reason"] = f"domain_cap:{domain}"
            continue

        # Passed all checks
        seen_norm_urls.add(norm)
        seen_titles.append(norm_title)
        seen_dp_keys.add(dp_key)
        c["is_duplicate"] = False
        c["duplicate_reason"] = ""
        result.append(c)

    return result
