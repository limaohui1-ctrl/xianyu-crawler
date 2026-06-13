"""
Quality scoring — assess the quality of a ParseResult on a 0-100 scale.

Quality is assessed across multiple dimensions:
  - Content completeness (how many fields have data)
  - Content richness (text length, image count, structured data)
  - Data quality (price format, time format, link validity)
  - Source quality (parser used, fetch quality)

Each dimension contributes to a weighted total score.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
import re

from acs.core.result_model import ParseResult


# ── Scoring weights ─────────────────────────────────────────────

# Each dimension is scored 0-100, then weighted
QUALITY_WEIGHTS = {
    "completeness": 0.35,    # How many fields are filled
    "richness": 0.30,        # Content volume and depth
    "data_quality": 0.20,    # Format correctness
    "source_quality": 0.15,  # Parser and fetch reliability
}


@dataclass
class QualityScore:
    """Detailed quality breakdown for a ParseResult."""

    total: int = 0                  # 0-100
    completeness_score: int = 0    # 0-100
    richness_score: int = 0        # 0-100
    data_quality_score: int = 0    # 0-100
    source_quality_score: int = 0  # 0-100
    label: str = "low"             # high | medium | low
    details: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "completeness": self.completeness_score,
            "richness": self.richness_score,
            "data_quality": self.data_quality_score,
            "source_quality": self.source_quality_score,
            "label": self.label,
            "details": self.details,
        }


def score_quality(result: ParseResult) -> QualityScore:
    """Assess the quality of a ParseResult.

    Args:
        result: The ParseResult to score

    Returns:
        QualityScore with breakdown
    """
    score = QualityScore()

    score.completeness_score = _score_completeness(result)
    score.richness_score = _score_richness(result)
    score.data_quality_score = _score_data_quality(result)
    score.source_quality_score = _score_source_quality(result)

    # Weighted total
    score.total = int(round(
        score.completeness_score * QUALITY_WEIGHTS["completeness"] +
        score.richness_score * QUALITY_WEIGHTS["richness"] +
        score.data_quality_score * QUALITY_WEIGHTS["data_quality"] +
        score.source_quality_score * QUALITY_WEIGHTS["source_quality"]
    ))

    # Clamp
    score.total = max(0, min(100, score.total))

    # Label
    if score.total >= 70:
        score.label = "high"
    elif score.total >= 35:
        score.label = "medium"
    else:
        score.label = "low"

    return score


def _score_completeness(result: ParseResult) -> int:
    """Score based on how many content fields have data."""
    fields = {
        "title": result.title,
        "body": result.body,
        "price": result.price,
        "author": result.author,
        "published_time": result.published_time,
        "images": bool(result.images),
        "links": bool(result.links),
        "tables": bool(result.tables),
        "structured_data": bool(result.structured_data),
    }

    filled = sum(1 for v in fields.values() if v)
    total = len(fields)

    if total == 0:
        return 0
    return int(round(filled / total * 100))


def _score_richness(result: ParseResult) -> int:
    """Score based on content depth and volume."""
    score = 0

    # Body length
    body_len = len(result.body) if result.body else 0
    if body_len >= 5000:
        score += 40
    elif body_len >= 1000:
        score += 30
    elif body_len >= 200:
        score += 15
    elif body_len >= 50:
        score += 5

    # Image count
    img_count = len(result.images)
    if img_count >= 10:
        score += 25
    elif img_count >= 5:
        score += 15
    elif img_count >= 1:
        score += 5

    # Link count
    link_count = len(result.links)
    if link_count >= 20:
        score += 15
    elif link_count >= 5:
        score += 8
    elif link_count >= 1:
        score += 3

    # Structured data
    sd_count = len(result.structured_data)
    if sd_count >= 3:
        score += 20
    elif sd_count >= 1:
        score += 10

    return min(100, score)


def _score_data_quality(result: ParseResult) -> int:
    """Score based on data format correctness."""
    score = 50  # Start neutral

    # Price format
    if result.price:
        if re.match(r'^\d+\.?\d*$', result.price):
            score += 15
        elif re.match(r'^[¥￥$€£]\s*\d+', result.price):
            score += 10
    else:
        score -= 0  # Neutral — price may not be applicable

    # Time format
    if result.published_time:
        if re.match(r'\d{4}-\d{2}-\d{2}', result.published_time):
            score += 15
        elif re.match(r'\d{4}[/年]\d{1,2}', result.published_time):
            score += 8
    else:
        score -= 0

    # Title quality
    if result.title:
        # Too short
        if len(result.title) < 3:
            score -= 10
        # Contains escaped HTML
        elif re.search(r'&[a-z]+;', result.title):
            score -= 5
        # Reasonable length
        elif 5 <= len(result.title) <= 200:
            score += 5
    else:
        score -= 10

    # Body quality
    if result.body:
        # Too short
        if len(result.body) < 50:
            score -= 15
        # All uppercase (likely boilerplate)
        if result.body.isupper() and len(result.body) > 100:
            score -= 10
    else:
        score -= 10

    # Image URL quality
    broken_imgs = sum(1 for img in result.images if not img.startswith(("http://", "https://", "//")))
    if broken_imgs > 0:
        score -= min(10, broken_imgs * 3)

    # Link URL quality
    broken_links = sum(1 for link in result.links if not link.startswith(("http://", "https://")))
    if broken_links > 0 and len(result.links) > 0:
        score -= min(10, int(broken_links / max(len(result.links), 1) * 30))

    return max(0, min(100, score))


def _score_source_quality(result: ParseResult) -> int:
    """Score based on parser and fetch reliability."""
    score = 60  # Start neutral

    # Fetch quality
    if result.fetch_quality == "full":
        score += 20
    elif result.fetch_quality.startswith("degraded"):
        score -= 10
    elif result.fetch_quality == "failed":
        score -= 30

    # Parser used
    parser_bonus = {
        "jsonld": 15,
        "json": 10,
        "css": 10,
        "xpath": 8,
        "fallback": -5,
        "none": -20,
    }
    score += parser_bonus.get(result.parser_used, 0)

    # Error indicator
    if result.error:
        score -= 15

    return max(0, min(100, score))


def score_results(results: List[ParseResult]) -> List[dict]:
    """Score a batch of results and return summary."""
    scored = []
    for r in results:
        qs = score_quality(r)
        scored.append({
            "url": r.url,
            "quality": qs.to_dict(),
        })
    return scored
