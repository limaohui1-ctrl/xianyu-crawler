"""
Tests for acs.fetcher — http_client and response_classifier.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from acs.fetcher.http_client import HttpClient, HttpResponse, DEFAULT_USER_AGENT
from acs.fetcher.response_classifier import (
    classify_response, ResponseClassification,
    ContentType, PageKind,
)


# ═══════════════════════════════════════════════════════════════════
# http_client tests
# ═══════════════════════════════════════════════════════════════════

class TestHttpClient:
    """Tests for HttpClient."""

    def test_init_defaults(self):
        client = HttpClient()
        assert client.user_agent == DEFAULT_USER_AGENT
        assert client.timeout == 30
        assert client.max_retries == 3

    def test_init_custom(self):
        client = HttpClient(
            user_agent="TestAgent/1.0",
            timeout=10,
            max_retries=1,
            extra_headers={"X-Custom": "yes"},
        )
        assert client.user_agent == "TestAgent/1.0"
        assert client.timeout == 10
        assert client.max_retries == 1
        assert client.extra_headers == {"X-Custom": "yes"}

    def test_response_properties(self):
        resp = HttpResponse(
            url="http://example.com",
            status_code=200,
            body="<html>Hello</html>",
            body_bytes=b"<html>Hello</html>",
            content_type="text/html; charset=utf-8",
        )
        assert resp.is_success
        assert not resp.is_redirect
        assert not resp.is_client_error
        assert not resp.is_server_error
        assert resp.size_bytes == 18
        assert "Hello" in resp.text_preview

    def test_response_error_properties(self):
        resp = HttpResponse(url="http://x.com", status_code=404)
        assert not resp.is_success
        assert resp.is_client_error

        resp500 = HttpResponse(url="http://x.com", status_code=503)
        assert resp500.is_server_error

    def test_response_to_dict(self):
        resp = HttpResponse(url="http://x.com", status_code=200, body="ok")
        d = resp.to_dict()
        assert d["url"] == "http://x.com"
        assert d["status_code"] == 200

    def test_encoding_detection(self):
        # UTF-8 from content-type
        enc = HttpClient._detect_encoding("text/html; charset=utf-8", b"")
        assert enc == "utf-8"

        enc = HttpClient._detect_encoding("text/html; charset=gb2312", b"")
        assert enc == "gb2312"

        # BOM detection
        enc = HttpClient._detect_encoding("text/html", b"\xef\xbb\xbf<html>")
        assert enc == "utf-8"

        # Default
        enc = HttpClient._detect_encoding("text/html", b"<html>")
        assert enc == "utf-8"

    def test_live_get(self):
        """Integration test — make a real HTTP request."""
        client = HttpClient(timeout=10)
        resp = client.get("http://httpbin.org/get?test=1")
        assert resp.is_success
        assert resp.status_code == 200
        assert "test" in resp.body
        assert resp.elapsed_seconds > 0


# ═══════════════════════════════════════════════════════════════════
# response_classifier tests
# ═══════════════════════════════════════════════════════════════════

class TestResponseClassifier:

    def test_classify_html(self):
        html = "<!DOCTYPE html><html><head><title>Test</title></head><body><p>Hi</p></body></html>"
        c = classify_response("http://example.com", html, 200, "text/html")
        assert c.content_type == ContentType.HTML
        assert c.page_kind == PageKind.NORMAL
        assert c.is_parseable
        assert not c.should_skip

    def test_classify_json(self):
        body = '{"name": "test", "price": 19.99}'
        c = classify_response("http://api.example.com/data", body, 200, "application/json")
        assert c.content_type == ContentType.JSON
        assert c.is_parseable

    def test_classify_empty(self):
        c = classify_response("http://x.com", "", 200)
        assert c.content_type == ContentType.EMPTY
        assert c.is_empty
        assert c.should_skip

    def test_classify_captcha(self):
        html = "<html><body><div>Please complete the captcha</div><div class='g-recaptcha'></div></body></html>"
        c = classify_response("http://x.com", html, 200, "text/html")
        assert c.page_kind == PageKind.CAPTCHA_PAGE
        assert c.should_skip

    def test_classify_login(self):
        html = "<html><body><form><input type='password' name='password'></form>请登录</body></html>"
        c = classify_response("http://x.com", html, 200, "text/html")
        assert c.page_kind == PageKind.LOGIN_PAGE
        assert c.needs_browser

    def test_classify_error_page(self):
        html = "<html><body><h1>404 Page Not Found</h1></body></html>"
        c = classify_response("http://x.com", html, 200, "text/html")
        assert c.page_kind == PageKind.ERROR_PAGE

    def test_classify_maintenance(self):
        html = "<html><body><h1>网站维护中</h1></body></html>"
        c = classify_response("http://x.com", html, 200, "text/html")
        assert c.page_kind == PageKind.MAINTENANCE
        assert c.should_skip

    def test_http_status_warning(self):
        html = "<html><body>Error</body></html>"
        c = classify_response("http://x.com", html, 500)
        assert c.warnings

    def test_classification_dict(self):
        html = "<html><body>Test</body></html>"
        c = classify_response("http://x.com", html)
        d = c.to_dict()
        assert d["content_type"] == "html"
        assert d["is_parseable"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
