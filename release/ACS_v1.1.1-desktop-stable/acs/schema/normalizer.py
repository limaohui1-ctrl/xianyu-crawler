"""
Field normalizer — cleans and standardizes parsed field values.

Each field in ParseResult can benefit from normalization:
  - title: strip boilerplate suffixes (site names, separators)
  - price: extract numeric value, normalize currency
  - published_time: parse to ISO format
  - body: strip excessive whitespace
  - domain: normalize to lowercase, strip www prefix
  - images/links: deduplicate, resolve relative URLs

Normalizers are pure functions — they take a ParseResult and return a new one.
They're composable via normalize_result().
"""

from typing import Callable, List, Optional
from urllib.parse import urlparse, urljoin
import re
import datetime

from acs.core.result_model import ParseResult


# ── Individual field normalizers ─────────────────────────────────

def normalize_title(title: str) -> str:
    """Clean a title string.

    - Strip common boilerplate suffixes (site name, separators)
    - Collapse whitespace
    - Limit length
    """
    if not title:
        return ""

    title = title.strip()

    # Strip common boilerplate suffixes
    # Pattern: "Title - Site Name" or "Title | Site Name" or "Title — Site Name"
    separators = [
        r'\s*[-–—|:]\s*(?:[^|\-–—:]{2,40})$',   # " - Site Name"
        r'\s*[-–—|:]\s*$',                         # trailing separator
        r'\s*[|]\s*(?:[^|]{2,40})$',               # " | Site Name"
    ]
    for pat in separators:
        title = re.sub(pat, '', title)
    title = title.strip()

    # Collapse whitespace
    title = re.sub(r'\s+', ' ', title)

    # Remove repeated separators at end
    title = re.sub(r'\s*[-–—|:]\s*$', '', title)

    return title.strip()[:500]


def normalize_price(price: str) -> str:
    """Normalize a price string.

    - Extract numeric value
    - Normalize currency symbols
    - Returns empty string if unparseable
    """
    if not price or not price.strip():
        return ""

    price = price.strip()

    # Already a clean number
    if re.match(r'^\d+\.?\d*$', price):
        return price

    # Currency symbol + number: ¥19.99 → 19.99
    m = re.search(r'[¥￥$€£]\s*([\d,]+\.?\d*)', price)
    if m:
        return m.group(1).replace(',', '')

    # Number + CN suffix: 19.99元 → 19.99
    m = re.search(r'([\d,]+\.?\d*)\s*[元块]', price)
    if m:
        return m.group(1).replace(',', '')

    # Just extract any number
    m = re.search(r'([\d,]+\.?\d*)', price)
    if m:
        return m.group(1).replace(',', '')

    return price[:60]


def normalize_published_time(time_str: str) -> str:
    """Normalize a time string to ISO-like YYYY-MM-DD HH:MM:SS format.

    Handles common formats:
      - 2024-01-15T10:30:00+00:00
      - 2024年1月15日
      - 2024/01/15
      - 2024-01-15
      - Jan 15, 2024
    """
    if not time_str or not time_str.strip():
        return ""

    time_str = time_str.strip()

    # ISO 8601
    m = re.match(r'(\d{4})-(\d{1,2})-(\d{1,2})[T ](\d{1,2}):(\d{2})(?::(\d{2}))?', time_str)
    if m:
        parts = list(m.groups())
        if parts[5] is None:
            parts[5] = '00'
        return f"{parts[0]}-{parts[1].zfill(2)}-{parts[2].zfill(2)} {parts[3].zfill(2)}:{parts[4].zfill(2)}:{parts[5].zfill(2)}"

    # Chinese: 2024年1月15日
    m = re.match(r'(\d{4})年(\d{1,2})月(\d{1,2})日', time_str)
    if m:
        return f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)} 00:00:00"

    # Slashes: 2024/01/15
    m = re.match(r'(\d{4})/(\d{1,2})/(\d{1,2})', time_str)
    if m:
        return f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)} 00:00:00"

    # Dashes date only: 2024-01-15
    m = re.match(r'(\d{4})-(\d{1,2})-(\d{1,2})$', time_str)
    if m:
        return f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)} 00:00:00"

    return time_str[:100]


def normalize_domain(domain: str) -> str:
    """Normalize domain to lowercase, stripping www prefix."""
    if not domain:
        return ""
    domain = domain.lower().strip()
    domain = re.sub(r'^www\d*\.', '', domain)
    return domain


def normalize_body(body: str) -> str:
    """Normalize body text.

    - Collapse excessive whitespace
    - Remove leading/trailing blank lines
    - Limit length
    """
    if not body:
        return ""

    body = body.strip()
    body = re.sub(r'\r\n', '\n', body)
    body = re.sub(r'\r', '\n', body)
    body = re.sub(r'\t', ' ', body)
    body = re.sub(r' {3,}', '  ', body)
    body = re.sub(r'\n{3,}', '\n\n', body)
    return body[:20000]


def normalize_images(images: List[str], base_url: str = "") -> List[str]:
    """Deduplicate images and strip fragments."""
    seen = set()
    result = []
    for img in images:
        if not img:
            continue
        # Strip query params that are just cache busters
        # Keep ?format= but drop ?v=, ?t=, ?_=
        clean = re.sub(r'[?&](?:v|t|_|ts|ver|cb|_cb|_t)=\d+', '', img)
        clean = re.sub(r'[?&]$', '', clean)
        if clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result[:120]


def normalize_links(links: List[str], domain: str = "") -> List[str]:
    """Deduplicate links, exclude non-HTTP schemes."""
    seen = set()
    result = []
    for link in links:
        if not link:
            continue
        if not link.startswith(("http://", "https://")):
            continue
        # Strip fragment
        try:
            parsed = urlparse(link)
            clean = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            if parsed.query:
                clean += f"?{parsed.query}"
        except Exception:
            clean = link
        if clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result[:300]


# ── Composite normalizer ────────────────────────────────────────

def normalize_result(result: ParseResult) -> ParseResult:
    """Apply all normalizers to a ParseResult.

    Returns the same object (mutated in place) for convenience.
    """
    result.title = normalize_title(result.title)
    result.price = normalize_price(result.price)
    result.published_time = normalize_published_time(result.published_time)
    result.body = normalize_body(result.body)
    result.images = normalize_images(result.images, result.url)
    result.links = normalize_links(result.links, result.domain)

    # Normalize domain AFTER body/images/links normalizers (which may use it)
    result.domain = normalize_domain(result.domain)

    # Recompute content hash after normalization (but keep the normalized domain)
    result.build()
    # Restore the normalized domain (build() recomputes from URL)
    result.domain = normalize_domain(result.domain)
    return result


# ── Batch normalizer ────────────────────────────────────────────

def normalize_results(results: List[ParseResult]) -> List[ParseResult]:
    """Normalize a batch of results."""
    return [normalize_result(r) for r in results]
