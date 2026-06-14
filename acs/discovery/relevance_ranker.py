"""RelevanceRanker — score and sort candidate URLs by relevance to topic/keywords."""
from typing import List


class RelevanceRanker:
    """Score candidates by keyword match in title, snippet, and domain trust."""

    def rank(self, candidates: List["CandidateUrl"], topic: str,
             keywords: List[str]) -> List["CandidateUrl"]:
        """Score and sort candidates. Blocked items are pushed to the bottom.

        Returns a new sorted list (does not mutate input).
        """
        if not candidates:
            return []

        scored = []
        for c in candidates:
            score = self._score(c, topic, keywords)
            c.estimated_relevance = min(score, 1.0)
            scored.append(c)

        # Sort: allowed/needs_review first by relevance descending,
        # blocked last (also sorted by relevance within blocked)
        return sorted(scored, key=lambda c: (
            0 if c.compliance_status != "blocked" else 1,
            -c.estimated_relevance
        ))

    def _score(self, candidate: "CandidateUrl", topic: str,
               keywords: List[str]) -> float:
        """Compute relevance score 0-1."""
        title = (candidate.title or "").lower()
        snippet = (candidate.snippet or "").lower()
        topic_lower = topic.lower()
        kws = [k.lower() for k in keywords if k.strip()]

        score = 0.0

        # Title match (weight: 0.4)
        if topic_lower in title:
            score += 0.4
        else:
            for kw in kws:
                if kw in title:
                    score += 0.15
                    break

        # Snippet match (weight: 0.3)
        if topic_lower in snippet:
            score += 0.3
        else:
            match_count = sum(1 for kw in kws if kw in snippet)
            score += min(match_count * 0.08, 0.3)

        # Keyword count (weight: 0.2)
        all_text = title + " " + snippet
        kw_hits = sum(1 for kw in kws if kw in all_text)
        score += min(kw_hits * 0.05, 0.2)

        # Domain trust bonus (weight: 0.1)
        domain = candidate.source_domain or ""
        if any(domain.endswith(s) for s in [".gov", ".edu", ".gov.cn", ".edu.cn"]):
            score += 0.1
        elif any(domain.endswith(s) for s in [".org", ".org.cn"]):
            score += 0.05

        return score
