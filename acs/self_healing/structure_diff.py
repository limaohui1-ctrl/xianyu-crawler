"""
Structure diff — detects DOM structure changes between old and new page versions.

Compares:
  - DOM node counts
  - Key selector presence/absence
  - Content area changes
  - JSON-LD structure changes

Outputs a change score and recommendation for AI repair.

Usage:
    from acs.self_healing.structure_diff import StructureDiffer

    differ = StructureDiffer(key_selectors={".title": "h1", ".price": "span.price"})
    diff = differ.compare(old_html, new_html)
    if diff.structure_changed:
        print(f"Change score: {diff.change_score}, recommend repair: {diff.recommend_ai_repair}")
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple
import re
import hashlib


# ── Known critical selectors by field ────────────────────────────

DEFAULT_KEY_SELECTORS: Dict[str, List[str]] = {
    "title": ["h1", "[class*=title]", "[id*=title]", "meta[property='og:title']"],
    "price": ["[class*=price]", "[id*=price]", "[itemprop='price']", "meta[property='product:price:amount']"],
    "body": ["article", "main", "[class*=content]", "[class*=article]", "[class*=body]", "[role='main']"],
    "author": ["[class*=author]", "[class*=byline]", "[itemprop='author']", "meta[name='author']"],
    "published_time": ["time[datetime]", "meta[property='article:published_time']"],
    "images": ["img[src]", "[class*=gallery] img"],
    "jsonld": ["script[type*='ld+json']"],
}


@dataclass
class SelectorStatus:
    """Status of a single selector after structure comparison."""
    selector: str = ""
    present_before: bool = False
    present_after: bool = False
    match_count_before: int = 0
    match_count_after: int = 0
    is_critical: bool = False

    @property
    def failed(self) -> bool:
        return self.present_before and not self.present_after

    @property
    def changed(self) -> bool:
        return self.present_before != self.present_after or abs(
            self.match_count_before - self.match_count_after) > 5


@dataclass
class StructureDiffResult:
    """Result of structure comparison."""

    site_id: str = ""
    url: str = ""
    structure_changed: bool = False
    change_score: float = 0.0              # 0.0 – 1.0
    failed_selectors: List[str] = field(default_factory=list)
    suspected_new_regions: List[str] = field(default_factory=list)
    field_changes: Dict[str, List[SelectorStatus]] = field(default_factory=dict)
    dom_node_count_before: int = 0
    dom_node_count_after: int = 0
    jsonld_changed: bool = False
    recommend_ai_repair: bool = False
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "site_id": self.site_id,
            "url": self.url,
            "structure_changed": self.structure_changed,
            "change_score": round(self.change_score, 4),
            "failed_selectors": self.failed_selectors,
            "suspected_new_regions": self.suspected_new_regions,
            "field_changes": {
                field: [{"selector": s.selector, "failed": s.failed, "changed": s.changed}
                        for s in statuses]
                for field, statuses in self.field_changes.items()
            },
            "dom_node_count_before": self.dom_node_count_before,
            "dom_node_count_after": self.dom_node_count_after,
            "jsonld_changed": self.jsonld_changed,
            "recommend_ai_repair": self.recommend_ai_repair,
            "details": self.details,
        }


class StructureDiffer:
    """Detects DOM structure changes between two versions of the same page.

    Args:
        key_selectors: Dict of field_name -> list of CSS selectors
    """

    def __init__(
        self,
        key_selectors: Optional[Dict[str, List[str]]] = None,
        dom_change_threshold: float = 0.3,
    ):
        self.key_selectors = key_selectors or DEFAULT_KEY_SELECTORS
        self.dom_change_threshold = dom_change_threshold

    # ── Main comparison ──────────────────────────────────────────

    def compare(
        self,
        old_html: str,
        new_html: str,
        url: str = "",
        site_id: str = "",
    ) -> StructureDiffResult:
        """Compare old and new HTML to detect structure changes.

        Args:
            old_html: Previous (known-good) HTML
            new_html: Current HTML to compare

        Returns:
            StructureDiffResult with change score and recommendations
        """
        result = StructureDiffResult(
            site_id=site_id,
            url=url,
        )

        if not old_html and not new_html:
            return result
        if not old_html:
            result.structure_changed = True
            result.change_score = 1.0
            result.recommend_ai_repair = True
            return result
        if not new_html:
            result.structure_changed = True
            result.change_score = 1.0
            result.recommend_ai_repair = True
            return result

        # ── DOM node count ──
        result.dom_node_count_before = self._count_nodes(old_html)
        result.dom_node_count_after = self._count_nodes(new_html)
        node_change = self._node_count_change(
            result.dom_node_count_before,
            result.dom_node_count_after,
        )

        # ── Selector comparison ──
        total_selectors = 0
        failed_selector_count = 0

        for field, selectors in self.key_selectors.items():
            field_statuses = []
            for selector in selectors:
                before_count = self._count_matches(old_html, selector)
                after_count = self._count_matches(new_html, selector)
                status = SelectorStatus(
                    selector=selector,
                    present_before=before_count > 0,
                    present_after=after_count > 0,
                    match_count_before=before_count,
                    match_count_after=after_count,
                    is_critical=(field in ("title", "price")),
                )
                field_statuses.append(status)
                total_selectors += 1
                if status.failed:
                    failed_selector_count += 1
                    result.failed_selectors.append(selector)
            result.field_changes[field] = field_statuses

        # ── JSON-LD change ──
        result.jsonld_changed = self._jsonld_changed(old_html, new_html)

        # ── Suspected new regions (selectors that appear now but didn't before) ──
        for field, statuses in result.field_changes.items():
            for s in statuses:
                if not s.present_before and s.present_after and s.is_critical:
                    result.suspected_new_regions.append(
                        f"{field}: {s.selector} (now {s.match_count_after} matches)"
                    )

        # ── Compute change score ──
        selector_change_rate = (failed_selector_count / max(total_selectors, 1))
        score = node_change * 0.3 + selector_change_rate * 0.5
        if result.jsonld_changed:
            score += 0.2

        result.change_score = min(1.0, score)
        result.structure_changed = result.change_score >= self.dom_change_threshold
        result.recommend_ai_repair = result.structure_changed and failed_selector_count > 0

        result.details = {
            "node_change_pct": round(node_change, 4),
            "selector_failure_rate": round(selector_change_rate, 4),
            "jsonld_changed": result.jsonld_changed,
            "total_selectors": total_selectors,
            "failed_selector_count": failed_selector_count,
        }

        return result

    # ── Quick check (HTML only, no old reference) ────────────────

    def check_current(self, html: str, url: str = "",
                      site_id: str = "") -> StructureDiffResult:
        """Check current HTML for obvious issues without an old reference.

        Returns a result focused on what's missing now.
        """
        result = StructureDiffResult(site_id=site_id, url=url)

        if not html:
            result.structure_changed = True
            result.change_score = 1.0
            result.recommend_ai_repair = True
            return result

        result.dom_node_count_after = self._count_nodes(html)

        # Check which key selectors are missing
        for field, selectors in self.key_selectors.items():
            field_statuses = []
            for selector in selectors:
                count = self._count_matches(html, selector)
                status = SelectorStatus(
                    selector=selector,
                    present_before=False,  # unknown
                    present_after=count > 0,
                    match_count_before=0,
                    match_count_after=count,
                    is_critical=(field in ("title", "price")),
                )
                field_statuses.append(status)
            result.field_changes[field] = field_statuses

        # Critical fields missing → structure issue
        missing_critical = 0
        for field, statuses in result.field_changes.items():
            if field not in ("title", "price", "body"):
                continue
            if all(not s.present_after for s in statuses):
                missing_critical += 1
                result.failed_selectors.extend([s.selector for s in statuses])

        if missing_critical >= 2:
            result.structure_changed = True
            result.change_score = 0.6
            result.recommend_ai_repair = True
        elif missing_critical == 1:
            result.structure_changed = True
            result.change_score = 0.35
            result.recommend_ai_repair = False
        else:
            result.structure_changed = False
            result.change_score = 0.0

        return result

    # ── Internals ────────────────────────────────────────────────

    @staticmethod
    def _count_nodes(html: str) -> int:
        """Count approximate DOM nodes."""
        if not html:
            return 0
        # Count opening tags as a rough proxy
        return len(re.findall(r'<\w+[\s>]', html))

    @staticmethod
    def _node_count_change(before: int, after: int) -> float:
        """Compute normalized node count change."""
        if before <= 0 and after <= 0:
            return 0.0
        if before <= 0 or after <= 0:
            return 1.0
        return min(1.0, abs(before - after) / max(before, after))

    @staticmethod
    def _count_matches(html: str, selector: str) -> int:
        """Count CSS selector matches in HTML (simple regex-based)."""
        if not html or not selector:
            return 0
        # Strip combinators for simple counting; full CSS parsing not needed
        # for structure diff purposes
        simple = selector.split()[-1]  # take last part
        # Count tag occurrences
        if simple.startswith("[") or simple.startswith(".") or simple.startswith("#"):
            return 0  # attribute/class/id selectors need BeautifulSoup for exact count
        # For tag selectors, count opening tags
        tag = simple.split("[")[0].split(".")[0].split("#")[0].strip()
        if not tag:
            return 0
        return len(re.findall(rf'<{tag}[\s>]', html, re.IGNORECASE))

    @staticmethod
    def _jsonld_changed(old_html: str, new_html: str) -> bool:
        """Check if JSON-LD blocks differ."""
        def _extract_jsonld(h):
            blocks = re.findall(
                r'<script[^>]*type\s*=\s*["\']application/ld\+json["\'][^>]*>(.*?)</script>',
                h or "", re.DOTALL | re.IGNORECASE
            )
            return hashlib.md5("|".join(blocks).encode()).hexdigest()

        if not old_html or not new_html:
            return False
        return _extract_jsonld(old_html) != _extract_jsonld(new_html)
