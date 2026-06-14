"""
content_deduplicator.py — detect and mark duplicate content.

Dedup dimensions:
  1. URL duplicate — exact same URL
  2. Title duplicate — same or very similar title
  3. Content similarity — high text overlap (Jaccard)
  4. Same domain over-representation — too many from one domain

Strategy: mark duplicates, never delete. Export can optionally filter them.
"""

import hashlib
import re
from typing import List, Dict, Optional


def normalize_for_dedup(text: str) -> str:
    """Normalize text for comparison: lowercase, strip whitespace, remove stop chars."""
    text = text.lower().strip()
    text = re.sub(r"[\s\u3000]+", " ", text)  # normalize whitespace
    text = re.sub(r"[^\w\u4e00-\u9fff]", "", text)  # keep alphanum + CJK
    return text


def title_similarity(t1: str, t2: str) -> float:
    """Jaccard similarity of character bigrams for two titles."""
    n1 = normalize_for_dedup(t1)
    n2 = normalize_for_dedup(t2)
    if not n1 or not n2:
        return 0.0
    b1 = set(n1[i : i + 2] for i in range(len(n1) - 1))
    b2 = set(n2[i : i + 2] for i in range(len(n2) - 1))
    if not b1 or not b2:
        return 0.0
    intersection = len(b1 & b2)
    union = len(b1 | b2)
    return intersection / union if union > 0 else 0.0


def text_similarity(t1: str, t2: str, max_len: int = 2000) -> float:
    """Jaccard similarity on word/shingle sets for two text bodies."""
    n1 = normalize_for_dedup(t1[:max_len])
    n2 = normalize_for_dedup(t2[:max_len])
    if not n1 or not n2:
        return 0.0
    # 3-gram shingles
    s1 = set(n1[i : i + 3] for i in range(0, len(n1) - 2, 2))
    s2 = set(n2[i : i + 3] for i in range(0, len(n2) - 2, 2))
    if not s1 or not s2:
        return 0.0
    intersection = len(s1 & s2)
    union = len(s1 | s2)
    return intersection / union if union > 0 else 0.0


def content_hash(text: str) -> str:
    """Quick content fingerprint."""
    return hashlib.sha256(
        normalize_for_dedup(text).encode("utf-8", errors="ignore")
    ).hexdigest()[:16]


def deduplicate(articles: List[dict],
                title_threshold: float = 0.80,
                text_threshold: float = 0.60,
                domain_max: int = 5) -> List[dict]:
    """
    Mark duplicate articles.

    Args:
        articles: List of ContentRecord dicts.
        title_threshold: Jaccard similarity threshold for title dedup.
        text_threshold: Jaccard similarity threshold for body dedup.
        domain_max: Max allowed articles from same domain before marking extras.

    Returns:
        Same list with added fields:
          - is_duplicate: bool
          - duplicate_of: index of original article (or -1)
          - duplicate_reason: str explaining why it's a duplicate
    """
    for item in articles:
        item["is_duplicate"] = False
        item["duplicate_of"] = -1
        item["duplicate_reason"] = ""

    seen_urls: Dict[str, int] = {}
    seen_hashes: Dict[str, int] = {}
    domain_counts: Dict[str, int] = {}

    for i, article in enumerate(articles):
        url = (article.get("url") or "").strip().lower()
        title = article.get("title", "")
        body = article.get("main_text", "")
        domain = article.get("source_domain", "")

        # ── 1. URL duplicate (exact match) ──
        if url and url in seen_urls:
            article["is_duplicate"] = True
            article["duplicate_of"] = seen_urls[url]
            article["duplicate_reason"] = "URL重复"
            continue
        if url:
            seen_urls[url] = i

        # ── 2. Content hash duplicate ──
        body_hash = content_hash(body) if body else ""
        if body_hash and body_hash in seen_hashes:
            article["is_duplicate"] = True
            article["duplicate_of"] = seen_hashes[body_hash]
            article["duplicate_reason"] = "正文完全相同"
            continue
        if body_hash:
            seen_hashes[body_hash] = i

        # ── 3. Title similarity duplicate ──
        for j in range(i - 1, max(i - 10, -1), -1):
            prev = articles[j]
            if prev.get("is_duplicate"):
                continue
            sim = title_similarity(title, prev.get("title", ""))
            if sim >= title_threshold:
                article["is_duplicate"] = True
                article["duplicate_of"] = j
                article["duplicate_reason"] = f"标题高度相似 (similarity={sim:.2f})"
                break
        if article["is_duplicate"]:
            continue

        # ── 4. Body similarity duplicate ──
        for j in range(i - 1, max(i - 10, -1), -1):
            prev = articles[j]
            if prev.get("is_duplicate"):
                continue
            sim = text_similarity(body, prev.get("main_text", ""))
            if sim >= text_threshold:
                article["is_duplicate"] = True
                article["duplicate_of"] = j
                article["duplicate_reason"] = f"正文高度相似 (similarity={sim:.2f})"
                break
        if article["is_duplicate"]:
            continue

        # ── 5. Domain over-representation ──
        if domain:
            domain_counts[domain] = domain_counts.get(domain, 0) + 1
            if domain_counts[domain] > domain_max:
                article["is_duplicate"] = True
                article["duplicate_of"] = -1
                article["duplicate_reason"] = f"同一域名({domain})结果过多"

    return articles


def filter_duplicates(articles: List[dict]) -> List[dict]:
    """Return only non-duplicate articles."""
    return [a for a in articles if not a.get("is_duplicate")]
