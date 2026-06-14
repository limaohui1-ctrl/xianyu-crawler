"""
Selector repair — generates candidate CSS/XPath selectors for failed fields.

Does NOT auto-apply changes.  All candidates have status="pending_review"
and require human confirmation before activation.

Strategy:
  1. Parse current HTML with BeautifulSoup
  2. For each failed field, search for candidate elements matching
     expected content patterns (heading tags, price patterns, etc.)
  3. Generate multiple candidate selectors ranked by confidence
  4. Output structured repair candidates with evidence

Usage:
    from acs.self_healing.selector_repair import SelectorRepairer

    repairer = SelectorRepairer()
    candidates = repairer.repair_field(
        field="title",
        old_selector="h1.product-title",
        html=current_html,
        ai_hint="iPhone 15 Pro Max",  # AI-extracted value to match
    )
"""

from dataclasses import dataclass as _dataclass, field as _field
from typing import Any, Dict, List, Optional, Tuple
import re


@_dataclass
class SelectorCandidate:
    """A single selector repair candidate."""

    selector: str = ""
    confidence: float = 0.0           # 0.0 – 1.0
    evidence: str = ""                # Why this selector is suggested
    match_count: int = 0
    sample_text: str = ""             # First matched element's text

    def to_dict(self) -> dict:
        return {
            "selector": self.selector,
            "confidence": round(self.confidence, 4),
            "evidence": self.evidence,
            "match_count": self.match_count,
            "sample_text": self.sample_text[:200],
        }


@_dataclass
class FieldRepairResult:
    """Repair results for a single field."""

    site_id: str = ""
    url: str = ""
    field: str = ""
    old_selector: str = ""
    candidate_selectors: List[SelectorCandidate] = _field(default_factory=list)
    ai_hint: str = ""                 # AI-parsed value to match against
    status: str = "pending_review"    # ALWAYS pending_review

    def to_dict(self) -> dict:
        return {
            "site_id": self.site_id,
            "url": self.url,
            "field": self.field,
            "old_selector": self.old_selector,
            "candidate_selectors": [c.to_dict() for c in self.candidate_selectors],
            "ai_hint": self.ai_hint,
            "status": self.status,
        }


class SelectorRepairer:
    """Generates selector repair candidates — always pending_review.

    Args:
        min_confidence: Minimum confidence to include a candidate
        max_candidates: Max candidates per field
    """

    def __init__(
        self,
        min_confidence: float = 0.3,
        max_candidates: int = 5,
    ):
        self.min_confidence = min_confidence
        self.max_candidates = max_candidates

    # ── Repair a single field ────────────────────────────────────

    def repair_field(
        self,
        field: str,
        old_selector: str,
        html: str,
        url: str = "",
        site_id: str = "",
        ai_hint: str = "",
    ) -> FieldRepairResult:
        """Generate candidate selectors for a failed field.

        Args:
            field: Field name (title, price, body, author, published_time)
            old_selector: The selector that stopped working
            html: Current page HTML
            url: Page URL
            site_id: Site identifier
            ai_hint: AI-extracted value to help match candidates

        Returns:
            FieldRepairResult with candidates, status="pending_review"
        """
        result = FieldRepairResult(
            site_id=site_id,
            url=url,
            field=field,
            old_selector=old_selector,
            ai_hint=ai_hint,
        )

        if not html:
            return result

        # Get candidate generators for this field type
        generators = self._get_generators(field)
        candidates = []

        for gen in generators:
            gen_candidates = gen(html, old_selector, ai_hint)
            candidates.extend(gen_candidates)

        # Deduplicate by selector
        seen = set()
        unique = []
        for c in sorted(candidates, key=lambda x: -x.confidence):
            if c.selector in seen:
                continue
            seen.add(c.selector)
            if c.confidence >= self.min_confidence:
                unique.append(c)
            if len(unique) >= self.max_candidates:
                break

        result.candidate_selectors = unique
        return result

    # ── Repair multiple fields ───────────────────────────────────

    def repair_fields(
        self,
        field_repairs: List[Dict[str, str]],
        html: str,
        url: str = "",
        site_id: str = "",
    ) -> List[FieldRepairResult]:
        """Repair multiple fields at once.

        Args:
            field_repairs: [{"field": "title", "old_selector": "h1", "ai_hint": "..."}, ...]
            html: Current page HTML
        """
        results = []
        for repair in field_repairs:
            result = self.repair_field(
                field=repair.get("field", ""),
                old_selector=repair.get("old_selector", ""),
                html=html,
                url=url,
                site_id=site_id,
                ai_hint=repair.get("ai_hint", ""),
            )
            results.append(result)
        return results

    # ── Field-specific candidate generators ──────────────────────

    def _get_generators(self, field: str) -> List:
        """Return candidate generation functions for a field type."""
        generators = {
            "title": [self._title_candidates],
            "price": [self._price_candidates],
            "body": [self._body_candidates],
            "author": [self._author_candidates],
            "published_time": [self._time_candidates],
        }
        return generators.get(field, [self._generic_candidates])

    # ── Title candidates ─────────────────────────────────────────

    def _title_candidates(self, html: str, old_selector: str,
                          ai_hint: str = "") -> List[SelectorCandidate]:
        candidates = []
        # h1 tags
        for m in re.finditer(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL | re.IGNORECASE):
            text = re.sub(r'<[^>]+>', '', m.group(1)).strip()
            if text:
                conf = 0.85
                if ai_hint and ai_hint.lower() in text.lower():
                    conf = 0.95
                candidates.append(SelectorCandidate(
                    selector="h1",
                    confidence=conf,
                    evidence=f"h1 text matches expected: {text[:80]}",
                    sample_text=text[:100],
                ))

        # og:title meta
        m = re.search(r'<meta[^>]*property=["\']og:title["\'][^>]*content=["\']([^"\']+)["\']', html, re.IGNORECASE)
        if m:
            candidates.append(SelectorCandidate(
                selector='meta[property="og:title"]',
                confidence=0.80,
                evidence="og:title meta tag present",
                sample_text=m.group(1)[:100],
            ))

        # Class-based title candidates
        for cls_pat in ["title", "product-title", "post-title", "entry-title", "heading"]:
            if cls_pat in old_selector.lower():
                continue
            m = re.search(rf'<[^>]*class=["\'][^"\']*{cls_pat}[^"\']*["\'][^>]*>(.*?)</[^>]+>', html, re.IGNORECASE)
            if m:
                text = re.sub(r'<[^>]+>', '', m.group(1)).strip()
                if text:
                    candidates.append(SelectorCandidate(
                        selector=f'[class*="{cls_pat}"]',
                        confidence=0.70,
                        evidence=f"Class pattern '{cls_pat}' found with text: {text[:80]}",
                        sample_text=text[:100],
                    ))

        return candidates

    # ── Price candidates ─────────────────────────────────────────

    def _price_candidates(self, html: str, old_selector: str,
                          ai_hint: str = "") -> List[SelectorCandidate]:
        candidates = []
        # Price patterns in HTML text
        for m in re.finditer(r'(?:¥|￥|\$|€|£|元)\s*([\d,]+\.?\d*)', html):
            candidates.append(SelectorCandidate(
                selector="text:price_pattern",
                confidence=0.65,
                evidence=f"Currency pattern found: {m.group(0)}",
                sample_text=m.group(0),
            ))

        # itemprop price
        m = re.search(r'<[^>]*itemprop=["\']price["\'][^>]*>(.*?)</[^>]+>', html, re.IGNORECASE)
        if m:
            candidates.append(SelectorCandidate(
                selector='[itemprop="price"]',
                confidence=0.90,
                evidence=f"Schema.org price itemprop found: {m.group(1).strip()[:80]}",
                sample_text=m.group(1).strip()[:100],
            ))

        # meta price
        m = re.search(r'<meta[^>]*property=["\']product:price:amount["\'][^>]*content=["\']([^"\']+)["\']', html, re.IGNORECASE)
        if m:
            candidates.append(SelectorCandidate(
                selector='meta[property="product:price:amount"]',
                confidence=0.85,
                evidence=f"Meta price found: {m.group(1)}",
                sample_text=m.group(1),
            ))

        # Class-based price selectors
        for cls_pat in ["price", "product-price", "sale-price", "current-price", "amount"]:
            m = re.search(rf'<[^>]*class=["\'][^"\']*{cls_pat}[^"\']*["\'][^>]*>(.*?)</[^>]+>', html, re.IGNORECASE)
            if m:
                text = re.sub(r'<[^>]+>', '', m.group(1)).strip()
                if re.search(r'\d', text):
                    candidates.append(SelectorCandidate(
                        selector=f'[class*="{cls_pat}"]',
                        confidence=0.70,
                        evidence=f"Price class '{cls_pat}' contains number: {text[:80]}",
                        sample_text=text[:100],
                    ))

        return candidates

    # ── Body candidates ──────────────────────────────────────────

    def _body_candidates(self, html: str, old_selector: str,
                         ai_hint: str = "") -> List[SelectorCandidate]:
        candidates = []
        body_sections = [
            ("article", 0.85),
            ("main", 0.80),
            ('[role="main"]', 0.80),
            ("content", 0.70),
            ("post-content", 0.70),
            ("article-body", 0.70),
            ("entry-content", 0.65),
            ("description", 0.60),
        ]
        for tag_or_class, base_conf in body_sections:
            if tag_or_class.startswith("["):
                m = re.search(rf'<[^>]*{tag_or_class[1:-1]}[^>]*>(.*?)</[^>]+>', html, re.DOTALL | re.IGNORECASE)
            elif " " not in tag_or_class:
                m = re.search(rf'<{tag_or_class}[^>]*>(.*?)</{tag_or_class}>', html, re.DOTALL | re.IGNORECASE)
            else:
                m = re.search(rf'<[^>]*class=["\'][^"\']*{tag_or_class}[^"\']*["\'][^>]*>(.*?)</[^>]+>', html, re.DOTALL | re.IGNORECASE)
            if m:
                text = re.sub(r'<[^>]+>', '', m.group(1)).strip()
                if len(text) > 50:
                    candidates.append(SelectorCandidate(
                        selector=tag_or_class if tag_or_class.startswith("[") else
                        f'[{tag_or_class}]' if " " in tag_or_class else tag_or_class,
                        confidence=base_conf,
                        evidence=f"Content section found, text length={len(text)}",
                        sample_text=text[:100],
                    ))
        return candidates

    # ── Author / time / generic candidates ───────────────────────

    def _author_candidates(self, html: str, old_selector: str,
                           ai_hint: str = "") -> List[SelectorCandidate]:
        candidates = []
        for pat in ["author", "byline", "writer", "seller"]:
            m = re.search(rf'<[^>]*class=["\'][^"\']*{pat}[^"\']*["\'][^>]*>(.*?)</[^>]+>', html, re.IGNORECASE)
            if m:
                text = re.sub(r'<[^>]+>', '', m.group(1)).strip()
                if text:
                    candidates.append(SelectorCandidate(
                        selector=f'[class*="{pat}"]',
                        confidence=0.65,
                        evidence=f"Author class '{pat}' text: {text[:80]}",
                        sample_text=text[:100],
                    ))
        return candidates

    def _time_candidates(self, html: str, old_selector: str,
                         ai_hint: str = "") -> List[SelectorCandidate]:
        candidates = []
        for tag in [r'<time[^>]*datetime=["\']([^"\']+)["\']', r'<time[^>]*>(.*?)</time>']:
            m = re.search(tag, html, re.IGNORECASE)
            if m:
                candidates.append(SelectorCandidate(
                    selector="time",
                    confidence=0.75,
                    evidence=f"Time element found: {m.group(1)[:80]}",
                    sample_text=m.group(1)[:100],
                ))
                break
        return candidates

    def _generic_candidates(self, html: str, old_selector: str,
                            ai_hint: str = "") -> List[SelectorCandidate]:
        if ai_hint:
            # Simple: search for the AI hint text and suggest nearby selectors
            escaped = re.escape(ai_hint[:50])
            m = re.search(escaped, html, re.IGNORECASE)
            if m:
                return [SelectorCandidate(
                    selector="text:contains(ai_hint)",
                    confidence=0.40,
                    evidence=f"AI hint text found in page: {ai_hint[:80]}",
                    sample_text=ai_hint[:100],
                )]
        return []
