"""
Provider errors — typed exceptions for AI provider failures.

All provider errors inherit from ProviderError so callers can
catch a single base class.  Error codes enable structured logging
and CostController integration.

Usage:
    from acs.provider.provider_errors import (
        ProviderError, ProviderTimeoutError, ProviderRateLimitError,
    )
"""


class ProviderError(Exception):
    """Base class for all AI provider errors."""
    code = "PROVIDER_ERROR"
    retryable = False

    def __init__(self, message: str = "", details: dict = None):
        super().__init__(message)
        self.details = details or {}

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "message": str(self),
            "retryable": self.retryable,
            "details": self.details,
        }


class ProviderTimeoutError(ProviderError):
    code = "PROVIDER_TIMEOUT"
    retryable = True


class ProviderRateLimitError(ProviderError):
    code = "PROVIDER_RATE_LIMIT"
    retryable = True

    def __init__(self, message: str = "", retry_after: float = 0, details: dict = None):
        super().__init__(message, details)
        self.retry_after = retry_after


class ProviderAuthError(ProviderError):
    code = "PROVIDER_AUTH"
    retryable = False


class ProviderBadRequestError(ProviderError):
    code = "PROVIDER_BAD_REQUEST"
    retryable = False


class ProviderServerError(ProviderError):
    code = "PROVIDER_SERVER_ERROR"
    retryable = True


class ProviderConfigError(ProviderError):
    code = "PROVIDER_CONFIG"
    retryable = False


class ProviderResponseError(ProviderError):
    """Unexpected / unparseable response."""
    code = "PROVIDER_RESPONSE_ERROR"
    retryable = False


class ProviderCostLimitError(ProviderError):
    code = "PROVIDER_COST_LIMIT"
    retryable = False


# ── Map HTTP status to provider error ────────────────────────────

def error_from_http_status(status: int, message: str = "",
                           retry_after: float = 0) -> ProviderError:
    """Create the appropriate ProviderError for an HTTP status code.

    Args:
        status: HTTP status code
        message: Error message
        retry_after: Seconds to wait before retry (from 429 header)

    Returns:
        Appropriate ProviderError subclass
    """
    if status == 429:
        return ProviderRateLimitError(message, retry_after=retry_after)
    if status == 401 or status == 403:
        return ProviderAuthError(message)
    if status == 400 or status == 422:
        return ProviderBadRequestError(message)
    if 500 <= status < 600:
        return ProviderServerError(message)
    return ProviderError(message or f"HTTP {status}")
