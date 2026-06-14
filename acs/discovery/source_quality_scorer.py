"""SourceQualityScorer — evaluate source domain authority and quality.

Scores gov/edu/org domains higher, known-quality sources higher,
commercial and suspicious domains lower.
"""
import re

# High-quality domain patterns
HIGH_QUALITY_PATTERNS = [
    r"\.gov\.cn$", r"\.gov\.",            # Government
    r"\.edu\.cn$", r"\.edu$", r"\.ac\.",  # Education
    r"\.org\.cn$", r"\.org$",             # Non-profit
    r"wikipedia\.org", r"un\.org", r"who\.int",
]

# Medium-quality domain patterns
MEDIUM_QUALITY_PATTERNS = [
    r"\.cn$",                             # Chinese domain (general)
    r"news\.", r"media",                  # News/media
    r"github\.io", r"gitlab\.io",
]

# Low-quality indicators
LOW_QUALITY_PATTERNS = [
    r"blogspot\." , r"wordpress\.",
    r"\.tk$", r"\.ml$", r"\.ga$",         # Free domains often spam
    r"forum\." , r"bbs\.",
]

# Known commercial — always low or blocked
COMMERCIAL_PATTERNS = [
    r"amazon\.", r"walmart\.", r"ebay\.", r"bestbuy\.",
    r"taobao\.", r"tmall\.", r"jd\.com", r"shop\.",
]


def score_source_quality(domain: str) -> float:
    """Score a domain's source quality from 0.0 (lowest) to 1.0 (highest).

    Args:
        domain: The source domain (e.g., "epb.gov.cn")

    Returns:
        Quality score 0.0–1.0
    """
    if not domain:
        return 0.3  # Unknown → medium-low

    domain_lower = domain.lower()

    # Commercial → very low
    for pat in COMMERCIAL_PATTERNS:
        if re.search(pat, domain_lower):
            return 0.1

    # Low quality → low
    for pat in LOW_QUALITY_PATTERNS:
        if re.search(pat, domain_lower):
            return 0.3

    # High quality → high
    for pat in HIGH_QUALITY_PATTERNS:
        if re.search(pat, domain_lower):
            return 0.95

    # Medium quality
    for pat in MEDIUM_QUALITY_PATTERNS:
        if re.search(pat, domain_lower):
            return 0.7

    # Default: neutral
    return 0.5
