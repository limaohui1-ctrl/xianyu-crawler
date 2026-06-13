"""
Schema validator — validates a ParseResult against the expected schema.

Checks:
  - Required fields are present (url)
  - Field types are correct
  - Field lengths are within bounds
  - Content looks valid (not just boilerplate)
  - Returns a validation report with errors and warnings
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import re

from acs.core.result_model import ParseResult


@dataclass
class ValidationIssue:
    """A single validation finding."""
    field: str = ""
    severity: str = "error"     # error | warning
    code: str = ""              # e.g. "MISSING_REQUIRED", "TYPE_MISMATCH"
    message: str = ""

    def to_dict(self) -> dict:
        return {
            "field": self.field,
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
        }


@dataclass
class ValidationReport:
    """Result of validating a ParseResult."""

    valid: bool = True
    errors: List[ValidationIssue] = field(default_factory=list)
    warnings: List[ValidationIssue] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return len(self.errors)

    @property
    def warning_count(self) -> int:
        return len(self.warnings)

    def add_error(self, field: str, code: str, message: str):
        self.errors.append(ValidationIssue(field=field, severity="error", code=code, message=message))
        self.valid = False

    def add_warning(self, field: str, code: str, message: str):
        self.warnings.append(ValidationIssue(field=field, severity="warning", code=code, message=message))

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "errors": [e.to_dict() for e in self.errors],
            "warnings": [w.to_dict() for w in self.warnings],
            "error_count": self.error_count,
            "warning_count": self.warning_count,
        }


# ── Field definitions ───────────────────────────────────────────

# Each field: (type, required, max_length, allow_empty)
FIELD_SCHEMA = {
    "url":             (str,  True,  2048, False),
    "domain":          (str,  False, 256,  True),
    "template_name":   (str,  False, 200,  True),
    "title":           (str,  False, 500,  True),
    "price":           (str,  False, 60,   True),
    "published_time":  (str,  False, 100,  True),
    "author":          (str,  False, 200,  True),
    "body":            (str,  False, 20000, True),
    "images":          (list, False, 120,  True),
    "links":           (list, False, 300,  True),
    "tables":          (list, False, 200,  True),
    "parser_used":     (str,  False, 50,   True),
    "fetch_quality":   (str,  False, 50,   True),
    "content_hash":    (str,  False, 64,   True),
    "completeness":    (int,  False, 100,  True),
    "error":           (str,  False, 2000, True),
}


def validate_result(result: ParseResult) -> ValidationReport:
    """Validate a single ParseResult against the schema.

    Args:
        result: The ParseResult to validate

    Returns:
        ValidationReport with errors and warnings
    """
    report = ValidationReport()

    for field, (expected_type, required, max_len, allow_empty) in FIELD_SCHEMA.items():
        value = getattr(result, field, None)

        # Required check
        if required and (value is None or (isinstance(value, str) and not value.strip())):
            report.add_error(field, "MISSING_REQUIRED", f"必填字段 '{field}' 缺失或为空")
            continue

        if value is None:
            continue

        # Type check
        if not isinstance(value, expected_type):
            report.add_error(
                field, "TYPE_MISMATCH",
                f"字段 '{field}' 类型错误: 期望 {expected_type.__name__}, 实际 {type(value).__name__}"
            )
            continue

        # Length check
        if isinstance(value, str) and len(value) > max_len:
            report.add_warning(
                field, "TOO_LONG",
                f"字段 '{field}' 长度 {len(value)} 超过限制 {max_len}"
            )

        if isinstance(value, list) and len(value) > max_len:
            report.add_warning(
                field, "TOO_MANY_ITEMS",
                f"字段 '{field}' 包含 {len(value)} 项, 超过限制 {max_len}"
            )

    # ── Semantic checks ──

    # URL format
    if result.url and not re.match(r'^https?://', result.url):
        report.add_error("url", "INVALID_URL", f"URL 格式无效: {result.url[:100]}")

    # Title looks like gibberish
    if result.title and len(result.title) < 2 and len(result.body) > 100:
        report.add_warning("title", "TOO_SHORT", "标题过短，可能未正确提取")

    # Body is all whitespace/boilerplate
    if result.body and result.body.strip():
        # Check if body is just navigation text
        boilerplate_patterns = [
            r'^(Home|首页|About|关于|Contact|联系|Login|登录|Register|注册|Menu|菜单)\s*$',
        ]
        for pat in boilerplate_patterns:
            if re.match(pat, result.body.strip()):
                report.add_warning("body", "BOILERPLATE", "正文内容疑似为导航/页脚文本")

    # Error field present — this is expected for failed fetches
    if result.error and result.fetch_quality == "failed":
        # This is expected, not a validation error
        pass

    return report


def validate_results(results: List[ParseResult]) -> Dict[str, Any]:
    """Validate a batch of results.

    Returns a summary dict.
    """
    reports = []
    valid_count = 0
    invalid_count = 0

    for result in results:
        report = validate_result(result)
        reports.append(report)
        if report.valid:
            valid_count += 1
        else:
            invalid_count += 1

    return {
        "total": len(results),
        "valid": valid_count,
        "invalid": invalid_count,
        "reports": [r.to_dict() for r in reports],
    }
