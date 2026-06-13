"""Tests for acs.provider.openai_compatible_client — HTTP mocking, JSON parsing, error handling."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest, json
from acs.provider.openai_compatible_client import OpenAICompatibleClient, DEFAULT_MODELS
from acs.provider.provider_config import ProviderConfig

class _MockClient(OpenAICompatibleClient):
    """Mock client that returns pre-configured responses."""
    def __init__(self, config=None, mock_responses=None, mock_error=None):
        super().__init__(config)
        self._responses = mock_responses or []
        self._error = mock_error
        self._call_idx = 0

    def _call_api(self, system_prompt, user_prompt, model, temperature, max_tokens):
        from acs.provider.ai_client import AIResponse
        if self._error:
            raise self._error
        if self._call_idx < len(self._responses):
            resp = self._responses[self._call_idx]
            self._call_idx += 1
            return resp
        return AIResponse(text="default", tokens={"prompt": 1, "completion": 1})

class TestOpenAICompatibleClient:
    def test_config_not_set(self):
        c = OpenAICompatibleClient(ProviderConfig())
        r = c.complete("s", "u")
        assert "not configured" in r.error.lower()

    def test_json_parsing(self):
        from acs.provider.ai_client import AIResponse
        fake = AIResponse(text='{"title":"Test"}', tokens={"prompt": 10, "completion": 5},
                          raw_response={"choices":[{"message":{"content":'{"title":"Test"}'}}],"usage":{"prompt_tokens":10,"completion_tokens":5}})
        c = _MockClient(ProviderConfig(base_url="http://x", api_key="k", model="gpt-4o-mini"), mock_responses=[fake])
        r = c.complete("s", "u")
        assert r.tokens["prompt"] == 10
        assert r.text

    def test_token_estimation(self):
        c = OpenAICompatibleClient(ProviderConfig(base_url="http://x", api_key="k", model="gpt-4o-mini"))
        cost = c.estimate_cost(1000, 500)
        assert cost > 0

    def test_parser_handles_no_choices(self):
        r = c = OpenAICompatibleClient.__new__(OpenAICompatibleClient)
        # Directly test _parse_response
        c.config = ProviderConfig(base_url="http://x", api_key="k", model="m")
        c._model_pricing = DEFAULT_MODELS.get("m", DEFAULT_MODELS["gpt-4o-mini"])
        resp = c._parse_response(json.dumps({"choices": []}))
        assert resp.text == ""
        assert "No choices" in resp.error

    def test_api_key_not_in_logs(self):
        config = ProviderConfig(base_url="http://x", api_key="sk-secret-123", model="m")
        safe = config.safe_repr()
        assert "sk-secret-123" not in str(safe)
        assert "***" in str(safe)

    def test_error_from_http_429(self):
        from acs.provider.provider_errors import error_from_http_status, ProviderRateLimitError
        err = error_from_http_status(429, "Too many requests")
        assert isinstance(err, ProviderRateLimitError)
        assert err.retryable

    def test_error_from_http_401(self):
        from acs.provider.provider_errors import error_from_http_status, ProviderAuthError
        err = error_from_http_status(401, "Unauthorized")
        assert isinstance(err, ProviderAuthError)
        assert not err.retryable

    def test_build_url_appends_completions(self):
        c = OpenAICompatibleClient(ProviderConfig(base_url="http://x/v1", api_key="k", model="m"))
        url = c._build_url()
        assert "/chat/completions" in url

    def test_build_headers_has_auth(self):
        c = OpenAICompatibleClient(ProviderConfig(base_url="http://x", api_key="sk-test", model="m"))
        h = c._build_headers()
        assert "Bearer sk-test" in h["Authorization"]

    def test_build_body_json_format(self):
        c = OpenAICompatibleClient(ProviderConfig(base_url="http://x", api_key="k", model="m"))
        body = c._build_body("sys", "user", "m", 0.0, 100)
        assert body["response_format"]["type"] == "json_object"
        assert len(body["messages"]) >= 1

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
