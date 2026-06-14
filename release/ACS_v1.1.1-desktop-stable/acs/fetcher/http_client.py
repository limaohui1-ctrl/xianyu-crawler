"""
HTTP client with retry, timeout, and user-agent rotation.

Provides a clean, testable interface for making HTTP requests.  Supports:
  - GET / POST with configurable headers
  - Automatic retry with exponential backoff
  - Timeout enforcement
  - Response object that carries both body and metadata

This module does NOT handle browser-based fetching (Playwright) — that remains
in the existing universal_core.py.  It's designed for static HTTP fetching only.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
import gzip
import io
import json
import time
import zlib


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)

DEFAULT_TIMEOUT = 30
MAX_RETRIES = 3
RETRY_DELAY_BASE = 1.5   # seconds — multiplied by 2^retry_count


# ── Response ────────────────────────────────────────────────────

@dataclass
class HttpResponse:
    """The result of a single HTTP request."""

    url: str = ""
    status_code: int = 0
    headers: Dict[str, str] = field(default_factory=dict)
    body: str = ""                  # decoded text
    body_bytes: bytes = b""         # raw bytes
    encoding: str = "utf-8"
    content_type: str = ""
    elapsed_seconds: float = 0.0
    retry_count: int = 0
    error: str = ""

    @property
    def is_success(self) -> bool:
        return 200 <= self.status_code < 300

    @property
    def is_redirect(self) -> bool:
        return 300 <= self.status_code < 400

    @property
    def is_client_error(self) -> bool:
        return 400 <= self.status_code < 500

    @property
    def is_server_error(self) -> bool:
        return 500 <= self.status_code < 600

    @property
    def size_bytes(self) -> int:
        return len(self.body_bytes)

    @property
    def text_preview(self) -> str:
        """First 500 chars of the body, for logging."""
        return self.body[:500]

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "status_code": self.status_code,
            "content_type": self.content_type,
            "encoding": self.encoding,
            "size_bytes": self.size_bytes,
            "elapsed_seconds": self.elapsed_seconds,
            "retry_count": self.retry_count,
            "error": self.error,
        }


# ── Client ──────────────────────────────────────────────────────

class HttpClient:
    """Simple HTTP client with retry and error handling.

    Usage:
        client = HttpClient()
        response = client.get("https://example.com")
        if response.is_success:
            print(response.body)
    """

    def __init__(
        self,
        user_agent: str = DEFAULT_USER_AGENT,
        timeout: int = DEFAULT_TIMEOUT,
        max_retries: int = MAX_RETRIES,
        extra_headers: Optional[Dict[str, str]] = None,
    ):
        self.user_agent = user_agent
        self.timeout = timeout
        self.max_retries = max_retries
        self.extra_headers = dict(extra_headers or {})

    def get(self, url: str, headers: Optional[Dict[str, str]] = None) -> HttpResponse:
        """Perform a GET request with retry logic."""
        return self._request("GET", url, headers=headers)

    def post(self, url: str, data: Optional[bytes] = None,
             json_data: Optional[Any] = None,
             headers: Optional[Dict[str, str]] = None) -> HttpResponse:
        """Perform a POST request with retry logic."""
        return self._request("POST", url, data=data, json_data=json_data, headers=headers)

    def _request(
        self,
        method: str,
        url: str,
        data: Optional[bytes] = None,
        json_data: Optional[Any] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> HttpResponse:
        """Core request method with retry."""

        # Build headers
        req_headers: Dict[str, str] = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
        }
        req_headers.update(self.extra_headers)
        req_headers.update(headers or {})

        # Prepare body
        body_bytes: Optional[bytes] = None
        if json_data is not None:
            body_bytes = json.dumps(json_data, ensure_ascii=False).encode("utf-8")
            req_headers["Content-Type"] = "application/json"
        elif data is not None:
            body_bytes = data

        last_error = ""
        for retry in range(self.max_retries + 1):
            t0 = time.time()
            try:
                req = Request(url, data=body_bytes, headers=req_headers, method=method)
                with urlopen(req, timeout=self.timeout) as resp:
                    raw = resp.read()
                    elapsed = round(time.time() - t0, 3)

                    # Decompress
                    content_encoding = resp.headers.get("Content-Encoding", "").lower()
                    if "gzip" in content_encoding:
                        raw = gzip.decompress(raw)
                    elif "deflate" in content_encoding:
                        raw = zlib.decompress(raw)

                    # Detect encoding
                    content_type = resp.headers.get("Content-Type", "")
                    encoding = self._detect_encoding(content_type, raw)

                    body = raw.decode(encoding, errors="replace")
                    return HttpResponse(
                        url=url,
                        status_code=resp.status,
                        headers=dict(resp.headers),
                        body=body,
                        body_bytes=raw,
                        encoding=encoding,
                        content_type=content_type,
                        elapsed_seconds=elapsed,
                        retry_count=retry,
                    )

            except HTTPError as e:
                elapsed = round(time.time() - t0, 3)
                last_error = str(e)
                # Read error body if available
                try:
                    error_body = e.read().decode("utf-8", errors="replace")[:1000]
                except Exception:
                    error_body = ""

                # Don't retry client errors (4xx) except 429
                if e.code and 400 <= e.code < 500 and e.code != 429:
                    return HttpResponse(
                        url=url,
                        status_code=e.code,
                        body=error_body,
                        body_bytes=error_body.encode("utf-8", errors="ignore"),
                        elapsed_seconds=elapsed,
                        retry_count=retry,
                        error=last_error,
                    )

                if retry < self.max_retries:
                    self._sleep(retry)

            except URLError as e:
                elapsed = round(time.time() - t0, 3)
                last_error = str(e)
                if retry < self.max_retries:
                    self._sleep(retry)

            except Exception as e:
                elapsed = round(time.time() - t0, 3)
                last_error = str(e)
                if retry < self.max_retries:
                    self._sleep(retry)

        # All retries exhausted
        return HttpResponse(
            url=url,
            status_code=0,
            elapsed_seconds=round(time.time() - t0 if 't0' in dir() else 0, 3),
            retry_count=self.max_retries,
            error=last_error,
        )

    @staticmethod
    def _sleep(retry_count: int):
        """Exponential backoff."""
        delay = RETRY_DELAY_BASE * (2 ** retry_count)
        time.sleep(min(delay, 30.0))

    @staticmethod
    def _detect_encoding(content_type: str, raw: bytes) -> str:
        """Extract charset from Content-Type header, fall back to utf-8."""
        import re
        match = re.search(r"charset=([^\s;]+)", content_type, re.IGNORECASE)
        if match:
            return match.group(1).strip().lower()
        # Check for BOM
        if raw.startswith(b"\xef\xbb\xbf"):
            return "utf-8"
        if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
            return "utf-16"
        return "utf-8"
