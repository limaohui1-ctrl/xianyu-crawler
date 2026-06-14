"""TopicCandidateRanker — rank topic-level candidates by relevance, quality, freshness.

Multi-dimensional scoring:
  - keyword relevance (title + snippet)
  - source quality (gov/edu > commercial)
  - content type match
  - compliance status penalty
  - freshness (optional)

Always pushes blocked candidates to the bottom.
"""
from typing import List
from .source_quality_scorer import score_source_quality


def _keyword_score(text: str, keywords: List[str]) -> float:
    """Score how many unique keywords appear in text."""
    if not keywords or not text:
        return 0.0
    lower = text.lower()
    hits = sum(1 for kw in keywords if kw.lower() in lower)
    return hits / len(keywords)


def rank_topic_candidates(
    candidates: List[dict],
    topic: str = "",
    keywords: List[str] = None,
    content_type: str = "",
    prefer_gov_edu: bool = True,
) -> List[dict]:
    """Rank candidates by multi-factor score. Blocked always last.

    Score weights:
      keyword_relevance: 0.35
      source_quality:    0.25
      content_type_match: 0.15
      title_specificity:  0.10
      compliance_bonus:   0.15

    Returns sorted list (best first, blocked last).
    """
    keywords = keywords or []
    all_words = [topic] + keywords if topic else keywords
    # dedup all_words
    seen = set()
    all_words = [w for w in all_words if not (w in seen or seen.add(w))]

    scored = []
    for c in candidates:
        # Base scores
        title_score = _keyword_score(c.get("title", ""), all_words)
        snippet_score = _keyword_score(c.get("snippet", ""), all_words)
        krel = title_score * 0.7 + snippet_score * 0.3

        qual = score_source_quality(c.get("source_domain", ""))

        ct_match = 0.0
        if content_type and c.get("content_type", "") == content_type:
            ct_match = 1.0
        elif c.get("content_type", "") in ("pdf", "policy", "article", "case"):
            ct_match = 0.6  # Still valuable

        # Title specificity: prefer longer titles (less spam)
        tlen = len(c.get("title", ""))
        title_spec = min(tlen / 80.0, 1.0)

        # Compliance bonus: allowed=1.0, needs_review=0.4, blocked=0.0
        cs = c.get("compliance_status", "allowed")
        compliance_bonus = {"allowed": 1.0, "needs_review": 0.4}.get(cs, 0.0)

        # Freshness placeholder
        freshness = 0.5

        total = (
            krel * 0.35 +
            qual * 0.25 +
            ct_match * 0.15 +
            title_spec * 0.10 +
            compliance_bonus * 0.15
        )

        c["_relevance"] = round(krel, 3)
        c["_quality"] = round(qual, 3)
        c["_total_score"] = round(total, 3)
        scored.append(c)

    # Sort: blocked → bottom, then by total_score desc
    scored.sort(key=lambda x: (
        0 if x.get("compliance_status") == "blocked" else 1,
        x.get("_total_score", 0),
    ), reverse=True)

    return scored
