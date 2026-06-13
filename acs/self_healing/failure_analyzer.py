"""
Failure analyzer — classifies parse failures into structured categories.

Analyzes parse results and error patterns to determine:
  - Failure type (request failure, selector failure, structure change, etc.)
  - Severity
  - Whether retry is recommended
  - Whether AI parser should be invoked
  - Whether selector repair is recommended

Output is always structured JSON — designed to feed into repair_planner.

Usage:
    from acs.self_healing.failure_analyzer import FailureAnalyzer

    fa = FailureAnalyzer()
    report = fa.analyze(parse_result, parse_attempts, error_records)
    print(report.failure_type, report.severity)
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from enum import Enum


class FailureType(str, Enum):
    """Canonical failure types."""
    REQUEST_FAILED = "request_failed"
    RESPONSE_EMPTY = "response_empty"
    HTTP_ERROR = "http_error"
    JSON_STRUCTURE_CHANGED = "json_structure_changed"
    HTML_STRUCTURE_CHANGED = "html_structure_changed"
    SELECTOR_FAILED = "selector_failed"
    FIELD_MISSING = "field_missing"
    AI_PARSER_FAILED = "ai_parser_failed"
    COST_LIMIT_EXCEEDED = "cost_limit_exceeded"
    LOW_QUALITY_PARSE = "low_quality_parse"
    UNKNOWN = "unknown"


class Severity(str, Enum):
    FATAL = "fatal"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class FailureReport:
    """Structured failure analysis result."""

    url: str = ""
    failure_type: FailureType = FailureType.UNKNOWN
    severity: Severity = Severity.LOW
    retryable: bool = False
    recommend_ai_parser: bool = False
    recommend_selector_repair: bool = False
    reason: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    suggestions: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "failure_type": self.failure_type.value,
            "severity": self.severity.value,
            "retryable": self.retryable,
            "recommend_ai_parser": self.recommend_ai_parser,
            "recommend_selector_repair": self.recommend_selector_repair,
            "reason": self.reason,
            "details": self.details,
            "suggestions": self.suggestions,
        }


class FailureAnalyzer:
    """Classifies parse failures and generates structured reports.

    Args:
        missing_field_threshold: How many consecutive failures before recommending AI
        low_quality_threshold: Completeness % below which quality is "low"
    """

    def __init__(
        self,
        missing_field_threshold: int = 3,
        low_quality_threshold: int = 20,
    ):
        self.missing_field_threshold = missing_field_threshold
        self.low_quality_threshold = low_quality_threshold

    # ── Main analysis ────────────────────────────────────────────

    def analyze(
        self,
        url: str = "",
        parse_result=None,
        parse_attempts: Optional[List] = None,
        error_records: Optional[List] = None,
        consecutive_field_failures: int = 0,
        structure_diff_result=None,
    ) -> FailureReport:
        """Analyze a parse failure and classify it.

        Args:
            url: Source URL
            parse_result: ParseResult from best-effort parser
            parse_attempts: List of ParseAttempt from parser_engine
            error_records: List of ErrorRecord
            consecutive_field_failures: Consecutive pages with missing key fields
            structure_diff_result: StructureDiffResult if available

        Returns:
            FailureReport with classification and recommendations
        """
        attempts = parse_attempts or []
        errors = error_records or []

        # ── 1. Request-level failures ──
        if errors:
            report = self._analyze_errors(url, errors)
            if report.failure_type != FailureType.UNKNOWN:
                return report

        # ── 2. All parsers failed → AI recommended ──
        if attempts and all(not a.success for a in attempts):
            return FailureReport(
                url=url,
                failure_type=FailureType.SELECTOR_FAILED,
                severity=Severity.MEDIUM,
                retryable=False,
                recommend_ai_parser=True,
                recommend_selector_repair=True,
                reason="All conventional parsers failed to extract content",
                details={"failed_parsers": [a.parser_name for a in attempts],
                         "errors": [a.error[:100] for a in attempts if a.error]},
                suggestions=["Try AI parser as fallback",
                             "Review page structure for changes",
                             "Check if page requires JavaScript rendering"],
            )

        # ── 3. Parse succeeded but quality is low → structure change or AI help ──
        if parse_result and hasattr(parse_result, 'completeness'):
            comp = parse_result.completeness
            missing = getattr(parse_result, 'missing_fields', [])

            if comp < self.low_quality_threshold and missing:
                return FailureReport(
                    url=url,
                    failure_type=FailureType.LOW_QUALITY_PARSE,
                    severity=Severity.MEDIUM,
                    retryable=False,
                    recommend_ai_parser=True,
                    recommend_selector_repair=len(missing) >= 3,
                    reason=f"Low completeness ({comp}%), missing: {missing}",
                    details={"completeness": comp, "missing_fields": missing},
                    suggestions=["Try AI parser to fill missing fields",
                                 "Check if page structure changed",
                                 "Review selector effectiveness"],
                )

            if comp < self.low_quality_threshold:
                return FailureReport(
                    url=url,
                    failure_type=FailureType.LOW_QUALITY_PARSE,
                    severity=Severity.LOW,
                    retryable=False,
                    recommend_ai_parser=False,
                    recommend_selector_repair=False,
                    reason=f"Low completeness ({comp}%) but no specific field gaps",
                    details={"completeness": comp},
                )

        # ── 4. Specific fields consistently missing → selector repair ──
        if consecutive_field_failures >= self.missing_field_threshold:
            return FailureReport(
                url=url,
                failure_type=FailureType.FIELD_MISSING,
                severity=Severity.MEDIUM,
                retryable=False,
                recommend_ai_parser=True,
                recommend_selector_repair=True,
                reason=f"Field(s) missing for {consecutive_field_failures} consecutive pages",
                details={"consecutive_failures": consecutive_field_failures},
                suggestions=["Generate selector repair candidates",
                             "Use AI parser to fill gaps"],
            )

        # ── 5. Structure diff detected change ──
        if structure_diff_result and structure_diff_result.structure_changed:
            return FailureReport(
                url=url,
                failure_type=FailureType.HTML_STRUCTURE_CHANGED,
                severity=Severity.MEDIUM,
                retryable=False,
                recommend_ai_parser=True,
                recommend_selector_repair=True,
                reason=f"DOM structure changed (score={structure_diff_result.change_score:.2f})",
                details={
                    "change_score": structure_diff_result.change_score,
                    "failed_selectors": structure_diff_result.failed_selectors,
                },
                suggestions=["Review selector candidates",
                             "Run AI parser for current structure",
                             "Update site template selectors"],
            )

        # ── 6. No specific failure detected ──
        return FailureReport(
            url=url,
            failure_type=FailureType.UNKNOWN if not parse_result else FailureType.LOW_QUALITY_PARSE,
            severity=Severity.LOW,
            retryable=True,
            recommend_ai_parser=False,
            recommend_selector_repair=False,
            reason="No specific failure pattern detected",
        )

    # ── Batch analysis ───────────────────────────────────────────

    def analyze_batch(
        self,
        results: List,
        error_logs: Optional[List] = None,
    ) -> List[FailureReport]:
        """Analyze a batch of parse results."""
        reports = []
        consecutive_field_missing = 0

        for i, result in enumerate(results):
            prev_missing = consecutive_field_missing

            if result.error or (hasattr(result, 'completeness') and
                                result.completeness < self.low_quality_threshold):
                consecutive_field_missing += 1
            else:
                consecutive_field_missing = 0

            report = self.analyze(
                url=getattr(result, 'url', f"item_{i}"),
                parse_result=result,
                consecutive_field_failures=consecutive_field_missing,
            )
            reports.append(report)

        return reports

    # ── Internals ────────────────────────────────────────────────

    def _analyze_errors(self, url: str, errors: List) -> FailureReport:
        """Classify based on error records."""
        for err in errors:
            if not hasattr(err, 'category') and isinstance(err, dict):
                cat = err.get("category", "")
            else:
                cat = getattr(err, 'category', type(err).__name__) if hasattr(err, 'category') else ""

            cat_str = str(cat).lower()

            # HTTP errors (4xx/5xx) → request failure
            if any(kw in cat_str for kw in ("http", "network", "dns", "timeout")):
                return FailureReport(
                    url=url,
                    failure_type=FailureType.HTTP_ERROR if "http" in cat_str else FailureType.REQUEST_FAILED,
                    severity=Severity.HIGH if "5" in str(getattr(err, 'http_status', '')) else Severity.MEDIUM,
                    retryable="5" in str(getattr(err, 'http_status', '')),
                    recommend_ai_parser=False,
                    recommend_selector_repair=False,
                    reason=str(getattr(err, 'raw_error', getattr(err, 'error', str(err))))[:200],
                )

            # Parse errors → selector or structure
            if any(kw in cat_str for kw in ("parse", "selector", "no_match")):
                return FailureReport(
                    url=url,
                    failure_type=FailureType.SELECTOR_FAILED,
                    severity=Severity.MEDIUM,
                    retryable=False,
                    recommend_ai_parser=True,
                    recommend_selector_repair=True,
                    reason=str(getattr(err, 'raw_error', getattr(err, 'error', str(err))))[:200],
                )

        return FailureReport(url=url, failure_type=FailureType.UNKNOWN)
