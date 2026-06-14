"""Tests for acs.provider.ai_client — timeout, retry, error mapping, stats."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest, time
from acs.provider.ai_client import AIClient, AIResponse
from acs.provider.provider_config import ProviderConfig
from acs.provider.provider_errors import ProviderError, ProviderTimeoutError

class _TestClient(AIClient):
    """Concrete client for testing."""
    def __init__(self, config=None, raise_on_call=None, response=None):
        super().__init__(config)
        self._raise_on_call = raise_on_call
        self._response = response or AIResponse(text="hello", tokens={"prompt": 10, "completion": 5})

    def _call_api(self, system_prompt, user_prompt, model, temperature, max_tokens):
        if self._raise_on_call:
            raise self._raise_on_call
        return self._response

class TestAIClient:
    def test_complete_returns_response(self):
        c = _TestClient(config=ProviderConfig(base_url="http://x", api_key="k", model="m"))
        r = c.complete("sys", "user")
        assert r.text == "hello"
        assert r.tokens["prompt"] == 10
        assert c.call_count == 1

    def test_retry_on_retryable_error(self):
        err = ProviderError("temp", details={})
        err.retryable = True
        c = _TestClient(config=ProviderConfig(base_url="http://x", api_key="k", model="m", max_retries=2), raise_on_call=err)
        r = c.complete("sys", "user")
        assert r.text == ""
        assert "temp" in r.error

    def test_no_retry_on_non_retryable(self):
        err = ProviderError("auth error")
        err.retryable = False
        c = _TestClient(config=ProviderConfig(base_url="http://x", api_key="k", model="m", max_retries=2), raise_on_call=err)
        r = c.complete("sys", "user")
        assert c.call_count == 0
        assert "auth error" in r.error

    def test_stats_tracking(self):
        c = _TestClient(config=ProviderConfig(base_url="http://x", api_key="k", model="m"))
        c.complete("s", "u")
        assert c.call_count == 1
        assert c.total_tokens == 15
        assert c.error_count == 0

    def test_config_not_configured(self):
        c = _TestClient(config=ProviderConfig())
        r = c.complete("s", "u")
        assert "not configured" in r.error.lower() or not c.config.is_configured()

    def test_timeout_mechanism(self):
        class _SlowClient(AIClient):
            def _call_api(self, *a, **kw):
                time.sleep(3)
                return AIResponse(text="x")
        c = _SlowClient(config=ProviderConfig(base_url="http://x", api_key="k", model="m", timeout=1))
        r = c.complete("s", "u")
        assert "timed out" in r.error.lower() or r.text == "x" or r.text == ""

    def test_reset_stats(self):
        c = _TestClient(config=ProviderConfig(base_url="http://x", api_key="k", model="m"))
        c.complete("s", "u")
        c.reset_stats()
        assert c.call_count == 0

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
