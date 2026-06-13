"""
Error model — structured error classification for crawl failures.

Every failed fetch or parse produces an ErrorRecord with a canonical
category, severity, and actionable advice.  This replaces the string-based
error handling in classify_error() from universal_core.py.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
import time
import uuid


class ErrorCategory(str, Enum):
    """Canonical error categories for crawl / parse failures."""

    # ── network ──
    NETWORK_TIMEOUT = "network_timeout"
    NETWORK_DNS = "network_dns"
    NETWORK_REFUSED = "network_refused"
    NETWORK_RESET = "network_reset"
    NETWORK_GENERAL = "network_general"

    # ── HTTP ──
    HTTP_CLIENT_ERROR = "http_client_error"     # 4xx
    HTTP_SERVER_ERROR = "http_server_error"     # 5xx
    HTTP_REDIRECT_LOOP = "http_redirect_loop"

    # ── parsing ──
    PARSE_EMPTY = "parse_empty"                 # no content extracted
    PARSE_DECODE = "parse_decode"               # charset / encoding failure
    PARSE_INVALID_HTML = "parse_invalid_html"
    PARSE_INVALID_JSON = "parse_invalid_json"
    PARSE_NO_MATCH = "parse_no_match"           # selectors/xpaths matched nothing
    PARSE_GENERAL = "parse_general"

    # ── access / permissions ──
    ACCESS_AUTH = "access_auth"                 # 401/403 — authentication required
    ACCESS_BLOCKED = "access_blocked"           # IP blocked / rate limited (429)
    ACCESS_FORBIDDEN = "access_forbidden"       # 403 — not auth, straight block

    # ── content issues ──
    CONTENT_NOT_HTML = "content_not_html"       # got PDF/image/binary
    CONTENT_EMPTY = "content_empty"             # 200 OK but zero-length body
    CONTENT_TRUNCATED = "content_truncated"

    # ── system ──
    SYSTEM_MEMORY = "system_memory"
    SYSTEM_DISK = "system_disk"
    SYSTEM_INTERNAL = "system_internal"

    # ── unknown ──
    UNKNOWN = "unknown"


class ErrorSeverity(str, Enum):
    """How severe is this error?"""
    FATAL = "fatal"         # cannot continue this task at all
    RETRYABLE = "retryable"  # transient — retry might succeed
    DEGRADED = "degraded"   # partial success — result is usable but incomplete
    INFO = "info"            # non-error, just diagnostic


# ── Category classification rules ─────────────────────────────

_ERROR_PATTERNS = [
    # (keywords in lowercase error text, category, severity, advice)
    (
        ["timeout", "timed out", "超时"],
        ErrorCategory.NETWORK_TIMEOUT,
        ErrorSeverity.RETRYABLE,
        "请求超时。提高超时阈值或降低并发数后重试。",
    ),
    (
        ["name resolution", "dns", "getaddrinfo", "nodename"],
        ErrorCategory.NETWORK_DNS,
        ErrorSeverity.RETRYABLE,
        "DNS 解析失败。检查网址是否正确，网络是否连通。",
    ),
    (
        ["connection refused", "connection reset", "connection aborted"],
        ErrorCategory.NETWORK_REFUSED,
        ErrorSeverity.RETRYABLE,
        "连接被拒绝或重置。目标服务器可能拒绝请求，稍后重试或降低并发频率。",
    ),
    (
        ["connection", "network", "unreachable", "socket"],
        ErrorCategory.NETWORK_GENERAL,
        ErrorSeverity.RETRYABLE,
        "网络异常。检查代理/VPN 设置，确认网址可正常访问。",
    ),
    (
        ["401", "unauthorized"],
        ErrorCategory.ACCESS_AUTH,
        ErrorSeverity.FATAL,
        "需要身份认证。API Key 可能已过期或配置错误，请检查。",
    ),
    (
        ["403", "forbidden"],
        ErrorCategory.ACCESS_FORBIDDEN,
        ErrorSeverity.FATAL,
        "访问被拒绝(403)。页面可能有访问控制或 IP 限制。",
    ),
    (
        ["404", "not found"],
        ErrorCategory.HTTP_CLIENT_ERROR,
        ErrorSeverity.FATAL,
        "页面不存在(404)。确认网址正确。",
    ),
    (
        ["429", "too many requests", "rate limit"],
        ErrorCategory.ACCESS_BLOCKED,
        ErrorSeverity.RETRYABLE,
        "请求频率过高(429)。降低采集速度，增大访问间隔后重试。",
    ),
    (
        ["500", "502", "503", "504", "internal server", "bad gateway", "service unavailable", "gateway timeout"],
        ErrorCategory.HTTP_SERVER_ERROR,
        ErrorSeverity.RETRYABLE,
        "目标服务器错误(5xx)。稍后重试。",
    ),
    (
        ["decode", "encoding", "charset", "codec"],
        ErrorCategory.PARSE_DECODE,
        ErrorSeverity.DEGRADED,
        "编码/解码失败。已尝试回退编码，部分字符可能丢失。",
    ),
    (
        ["json", "jsondecode", "json parse", "invalid json"],
        ErrorCategory.PARSE_INVALID_JSON,
        ErrorSeverity.DEGRADED,
        "JSON 解析失败。返回内容可能不是有效 JSON，已回退到其他解析器。",
    ),
    (
        ["no content", "empty body", "zero-length"],
        ErrorCategory.CONTENT_EMPTY,
        ErrorSeverity.FATAL,
        "服务器返回空内容。可能需要浏览器渲染或 Cookie 支持。",
    ),
    (
        ["html", "parse error", "invalid markup", "malformed"],
        ErrorCategory.PARSE_INVALID_HTML,
        ErrorSeverity.DEGRADED,
        "HTML 结构异常。已尝试最佳解析，部分内容可能丢失。",
    ),
    (
        ["no match", "selector", "xpath", "css", "选择器"],
        ErrorCategory.PARSE_NO_MATCH,
        ErrorSeverity.DEGRADED,
        "选择器未匹配到内容。页面结构可能已变化，需更新选择器。",
    ),
    (
        ["memory", "out of memory", "allocation"],
        ErrorCategory.SYSTEM_MEMORY,
        ErrorSeverity.FATAL,
        "内存不足。减小采集规模或分批次处理。",
    ),
    (
        ["disk", "no space", "io error"],
        ErrorCategory.SYSTEM_DISK,
        ErrorSeverity.FATAL,
        "磁盘空间不足或 I/O 错误。清理磁盘后重试。",
    ),
]


@dataclass
class ErrorRecord:
    """A single crawl/parse error with classification."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    task_id: str = ""
    url: str = ""
    raw_error: str = ""                     # original exception message / traceback
    category: ErrorCategory = ErrorCategory.UNKNOWN
    severity: ErrorSeverity = ErrorSeverity.RETRYABLE
    advice: str = ""
    occurred_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%d %H:%M:%S"))
    http_status: Optional[int] = None
    retry_count: int = 0
    context: Dict[str, Any] = field(default_factory=dict)  # extra diagnostic info

    @classmethod
    def from_exception(cls, url: str, exc: Exception, task_id: str = "",
                       http_status: Optional[int] = None,
                       retry_count: int = 0) -> "ErrorRecord":
        """Build an ErrorRecord by classifying an exception."""
        error_text = str(exc)
        error_text_lower = error_text.lower()

        # Try to classify
        category = ErrorCategory.UNKNOWN
        severity = ErrorSeverity.RETRYABLE
        advice = ""

        for keywords, cat, sev, adv in _ERROR_PATTERNS:
            if any(kw in error_text_lower for kw in keywords):
                category = cat
                severity = sev
                advice = adv
                break

        if category == ErrorCategory.UNKNOWN:
            advice = "出现未知错误。查看完整错误信息，先重试；若仍失败，降低采集规模并检查网页是否可正常访问。"

        # If HTTP status is set and no category assigned, classify by status
        if category == ErrorCategory.UNKNOWN and http_status:
            if 400 <= http_status < 500:
                if http_status == 429:
                    category = ErrorCategory.ACCESS_BLOCKED
                    severity = ErrorSeverity.RETRYABLE
                    advice = "请求频率过高(429)。降低采集速度后重试。"
                elif http_status in (401, 403):
                    category = ErrorCategory.ACCESS_AUTH
                    severity = ErrorSeverity.FATAL
                    advice = f"访问被拒绝({http_status})。可能需要登录或 API Key。"
                else:
                    category = ErrorCategory.HTTP_CLIENT_ERROR
                    severity = ErrorSeverity.FATAL
                    advice = f"HTTP {http_status} 客户端错误。检查请求参数。"
            elif http_status >= 500:
                category = ErrorCategory.HTTP_SERVER_ERROR
                severity = ErrorSeverity.RETRYABLE
                advice = f"HTTP {http_status} 服务器错误。稍后重试。"
            elif http_status >= 300 and http_status < 400:
                category = ErrorCategory.HTTP_REDIRECT_LOOP
                severity = ErrorSeverity.FATAL
                advice = "重定向循环。检查 URL 是否正确。"

        return cls(
            task_id=task_id,
            url=url,
            raw_error=error_text[:2000],
            category=category,
            severity=severity,
            advice=advice,
            http_status=http_status,
            retry_count=retry_count,
        )

    @classmethod
    def from_error_text(cls, url: str, error_text: str, task_id: str = "",
                        http_status: Optional[int] = None) -> "ErrorRecord":
        """Build from a raw error string (not an exception)."""
        rec = cls(
            task_id=task_id,
            url=url,
            raw_error=error_text[:2000],
            http_status=http_status,
        )
        # Classify the text
        error_text_lower = error_text.lower()
        for keywords, cat, sev, adv in _ERROR_PATTERNS:
            if any(kw in error_text_lower for kw in keywords):
                rec.category = cat
                rec.severity = sev
                rec.advice = adv
                break
        return rec

    @property
    def is_retryable(self) -> bool:
        return self.severity == ErrorSeverity.RETRYABLE

    @property
    def is_fatal(self) -> bool:
        return self.severity == ErrorSeverity.FATAL

    @property
    def category_cn(self) -> str:
        """Chinese display name for the category."""
        _cn = {
            ErrorCategory.NETWORK_TIMEOUT: "网络超时",
            ErrorCategory.NETWORK_DNS: "DNS 解析失败",
            ErrorCategory.NETWORK_REFUSED: "连接被拒",
            ErrorCategory.NETWORK_RESET: "连接重置",
            ErrorCategory.NETWORK_GENERAL: "网络异常",
            ErrorCategory.HTTP_CLIENT_ERROR: "HTTP 客户端错误",
            ErrorCategory.HTTP_SERVER_ERROR: "HTTP 服务器错误",
            ErrorCategory.HTTP_REDIRECT_LOOP: "重定向循环",
            ErrorCategory.PARSE_EMPTY: "解析结果为空",
            ErrorCategory.PARSE_DECODE: "编码解码失败",
            ErrorCategory.PARSE_INVALID_HTML: "HTML 结构异常",
            ErrorCategory.PARSE_INVALID_JSON: "JSON 解析失败",
            ErrorCategory.PARSE_NO_MATCH: "选择器未匹配",
            ErrorCategory.PARSE_GENERAL: "解析失败",
            ErrorCategory.ACCESS_AUTH: "需要认证",
            ErrorCategory.ACCESS_BLOCKED: "请求被限流",
            ErrorCategory.ACCESS_FORBIDDEN: "访问被拒绝",
            ErrorCategory.CONTENT_NOT_HTML: "非 HTML 内容",
            ErrorCategory.CONTENT_EMPTY: "内容为空",
            ErrorCategory.CONTENT_TRUNCATED: "内容截断",
            ErrorCategory.SYSTEM_MEMORY: "内存不足",
            ErrorCategory.SYSTEM_DISK: "磁盘错误",
            ErrorCategory.SYSTEM_INTERNAL: "系统内部错误",
            ErrorCategory.UNKNOWN: "未知错误",
        }
        return _cn.get(self.category, "未知错误")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "task_id": self.task_id,
            "url": self.url,
            "category": self.category.value,
            "category_cn": self.category_cn,
            "severity": self.severity.value,
            "advice": self.advice,
            "occurred_at": self.occurred_at,
            "http_status": self.http_status,
            "retry_count": self.retry_count,
            "raw_error": self.raw_error,
            "context": self.context,
        }


@dataclass
class ErrorLog:
    """Aggregate error log for a batch / run."""

    errors: List[ErrorRecord] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.errors)

    @property
    def fatal_count(self) -> int:
        return sum(1 for e in self.errors if e.is_fatal)

    @property
    def retryable_count(self) -> int:
        return sum(1 for e in self.errors if e.is_retryable)

    @property
    def degraded_count(self) -> int:
        return sum(1 for e in self.errors if e.severity == ErrorSeverity.DEGRADED)

    def add(self, error: ErrorRecord):
        self.errors.append(error)

    def by_category(self) -> Dict[str, List[ErrorRecord]]:
        """Group errors by category."""
        groups: Dict[str, List[ErrorRecord]] = {}
        for e in self.errors:
            cat = e.category.value
            groups.setdefault(cat, []).append(e)
        return groups

    def summary(self) -> dict:
        return {
            "total": self.total,
            "fatal": self.fatal_count,
            "retryable": self.retryable_count,
            "degraded": self.degraded_count,
            "by_category": {
                cat: len(recs) for cat, recs in self.by_category().items()
            },
        }

    def to_list(self) -> List[dict]:
        return [e.to_dict() for e in self.errors]
