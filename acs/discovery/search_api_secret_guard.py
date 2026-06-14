"""SearchApiSecretGuard — ensure API keys are never logged, leaked, or exposed.

This module provides:
  - mask_key(): mask key for display (show last 4 chars only)
  - safe_headers(): build auth headers WITHOUT logging the key
  - sanitize_error(): strip Authorization headers from error messages
"""
import re


_KEY_PATTERN = re.compile(r"(api[_-]?key|authorization|token)\s*[:=]\s*[^\s,;]+", re.IGNORECASE)


def mask_key(key: str) -> str:
    """Return masked key for display: 'sk-...abcd'"""
    if not key:
        return "[NOT SET]"
    if len(key) <= 8:
        return "***"
    return f"{key[:3]}...{key[-4:]}"


def safe_headers(api_key: str, header_name: str = "Ocp-Apim-Subscription-Key") -> dict:
    """Build request headers. The key itself is NOT printed to any log."""
    return {header_name: api_key, "Accept": "application/json"}


def sanitize_error(exc: Exception) -> str:
    """Remove any API key fragments from error messages before display."""
    msg = str(exc)
    # Replace key=value and key: value patterns
    msg = _KEY_PATTERN.sub("[REDACTED]", msg)
    return msg


def redact_headers(headers: dict) -> dict:
    """Return a copy of headers dict with sensitive values redacted."""
    redacted = {}
    for k, v in headers.items():
        if any(s in k.lower() for s in ("key", "auth", "token", "secret")):
            redacted[k] = mask_key(str(v))
        else:
            redacted[k] = v
    return redacted
