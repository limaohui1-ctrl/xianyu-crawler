"""
OpenAI-compatible API client — HTTP client for any OpenAI-compatible endpoint.

Supports:
  - OpenAI, Azure OpenAI, local Ollama, custom relays
  - JSON-only response mode
  - Token usage tracking from response headers
  - API key masking (never appears in logs)
  - Structured error mapping via provider_errors

Usage:
    from acs.provider.openai_compatible_client import OpenAICompatibleClient
    from acs.provider.provider_config import ProviderConfig

    config = ProviderConfig(base_url="https://api.openai.com/v1", api_key="...", model="gpt-4o")
    client = OpenAICompatibleClient(config)
    resp = client.complete(system_prompt="You are helpful.", user_prompt="Hello")
"""

from typing import Any, Dict, Optional
import json
import re
import urllib.request
import urllib.error

from acs.provider.ai_client import AIClient, AIResponse
from acs.provider.provider_config import ProviderConfig
from acs.provider.provider_errors import (
    ProviderError,
    ProviderTimeoutError,
    ProviderAuthError,
    error_from_http_status,
)


# ── Default models (for testing, no real keys) ───────────────────

DEFAULT_MODELS: Dict[str, Dict[str, Any]] = {
    "gpt-4o": {
        "provider": "openai",
        "pricing": {"prompt_per_1k": 0.005, "completion_per_1k": 0.015},
    },
    "gpt-4o-mini": {
        "provider": "openai",
        "pricing": {"prompt_per_1k": 0.00015, "completion_per_1k": 0.0006},
    },
    "deepseek-chat": {
        "provider": "deepseek",
        "pricing": {"prompt_per_1k": 0.00014, "completion_per_1k": 0.00028},
    },
}


class OpenAICompatibleClient(AIClient):
    """OpenAI-compatible API client using urllib (no extra deps).

    Sends chat completions requests to any OpenAI-compatible endpoint.
    All API keys are read from config — never hard-coded.
    """

    def __init__(self, config: Optional[ProviderConfig] = None):
        super().__init__(config)
        self._model_pricing = DEFAULT_MODELS.get(
            self.config.model,
            {"provider": "unknown", "pricing": {"prompt_per_1k": 0.001, "completion_per_1k": 0.002}},
        )

    # ── Core implementation ──────────────────────────────────────

    def _call_api(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> AIResponse:
        """Send a chat completions request.

        Raises ProviderError subclasses on failure.
        """
        if not self.config.is_configured():
            raise ProviderError(
                "Provider not configured — set AI_BASE_URL, AI_API_KEY, AI_MODEL"
            )

        url = self._build_url()
        headers = self._build_headers()
        body = self._build_body(system_prompt, user_prompt, model, temperature, max_tokens)

        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(body).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.config.timeout) as resp:
                raw_data = resp.read().decode("utf-8")
                return self._parse_response(raw_data)

        except urllib.error.HTTPError as e:
            status = e.code
            error_body = ""
            retry_after = 0.0
            try:
                error_body = e.read().decode("utf-8")[:1000]
            except Exception:
                pass
            try:
                retry_after = float(e.headers.get("Retry-After", 0))
            except (ValueError, TypeError):
                pass

            raise error_from_http_status(status, str(e), retry_after=retry_after)

        except urllib.error.URLError as e:
            if "timeout" in str(e.reason).lower() or "timed out" in str(e.reason).lower():
                raise ProviderTimeoutError(str(e.reason))
            raise ProviderError(f"Network error: {e.reason}")

        except Exception as e:
            raise ProviderError(f"Unexpected error: {e}")

    # ── Request builders ─────────────────────────────────────────

    def _build_url(self) -> str:
        base = self.config.base_url.rstrip("/")
        if "/chat/completions" not in base:
            base = base + "/chat/completions"
        return base

    def _build_headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.config.api_key}",
            "User-Agent": "ACS-Agent/1.0",
        }

    def _build_body(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> dict:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})

        return {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }

    # ── Response parser ──────────────────────────────────────────

    def _parse_response(self, raw_data: str) -> AIResponse:
        """Parse OpenAI-compatible JSON response."""
        try:
            data = json.loads(raw_data)
        except json.JSONDecodeError as e:
            raise ProviderError(f"Invalid JSON response: {e}",
                                details={"raw": raw_data[:200]})

        # Check for error response
        if "error" in data and isinstance(data["error"], dict):
            err = data["error"]
            msg = err.get("message", str(err))
            raise ProviderError(msg, details={"api_error": err})

        choices = data.get("choices", [])
        if not choices:
            return AIResponse(
                text="",
                tokens={"prompt": 0, "completion": 0},
                error="No choices in response",
            )

        content = choices[0].get("message", {}).get("content", "")

        # Token usage
        usage = data.get("usage", {})
        tokens = {
            "prompt": usage.get("prompt_tokens", 0),
            "completion": usage.get("completion_tokens", 0),
        }

        # Estimate cost
        pricing = self._model_pricing.get("pricing", {})
        estimated_cost = (
            tokens["prompt"] * pricing.get("prompt_per_1k", 0.001) / 1000 +
            tokens["completion"] * pricing.get("completion_per_1k", 0.002) / 1000
        )

        return AIResponse(
            text=content,
            tokens=tokens,
            raw_response=data,
        )

    # ── Model pricing ────────────────────────────────────────────

    def estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        pricing = self._model_pricing.get("pricing", {})
        return (
            prompt_tokens * pricing.get("prompt_per_1k", 0.001) / 1000 +
            completion_tokens * pricing.get("completion_per_1k", 0.002) / 1000
        )
