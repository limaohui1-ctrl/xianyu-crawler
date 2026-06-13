"""
Pluggable AI client — reusable abstract base with retry, timeout, cost tracking.

Upgrade of acs.parser.ai_parser.AIClient with:
  - Configurable timeout, retries, max_tokens
  - Provider error translation
  - Automatic cost recording
  - API key masking in logs

Usage:
    from acs.provider.ai_client import AIClient
    from acs.provider.provider_config import ProviderConfig

    config = ProviderConfig.from_env()
    client = MyProvider(config)
    response = client.complete(system_prompt="...", user_prompt="...")
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
import time

from acs.provider.provider_config import ProviderConfig
from acs.provider.provider_errors import ProviderError


@dataclass
class AIResponse:
    """Structured AI provider response."""

    text: str = ""
    tokens: Dict[str, int] = field(default_factory=lambda: {"prompt": 0, "completion": 0})
    error: str = ""
    raw_response: Any = None


class AIClient(ABC):
    """Abstract AI provider client.

    Subclasses implement _call_api() for their specific provider.
    This base handles retry, timeout, and error mapping.

    Args:
        config: ProviderConfig with API settings
    """

    def __init__(self, config: Optional[ProviderConfig] = None):
        self.config = config or ProviderConfig()
        self._call_count: int = 0
        self._total_tokens: int = 0
        self._error_count: int = 0

    # ── Public interface ─────────────────────────────────────────

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str = "",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AIResponse:
        """Call the AI model with retry and error handling.

        Args:
            system_prompt: System message
            user_prompt: User message
            model: Override configured model
            temperature: Override configured temperature
            max_tokens: Override configured max_tokens

        Returns:
            AIResponse with text, token counts, and optional error
        """
        model = model or self.config.model
        temperature_val = temperature if temperature is not None else self.config.temperature
        max_tokens_val = max_tokens if max_tokens is not None else self.config.max_tokens

        last_error: Optional[ProviderError] = None

        for attempt in range(self.config.max_retries + 1):
            try:
                result = self._call_with_timeout(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    model=model,
                    temperature=temperature_val,
                    max_tokens=max_tokens_val,
                )
                self._call_count += 1
                self._total_tokens += result.tokens.get("prompt", 0) + result.tokens.get("completion", 0)
                return result

            except ProviderError as e:
                last_error = e
                self._error_count += 1

                if not e.retryable:
                    break

                if attempt < self.config.max_retries:
                    # Backoff: 1s, 2s, 4s
                    delay = 2 ** attempt
                    time.sleep(delay)
                    continue
                break

        # All attempts failed
        return AIResponse(
            text="",
            tokens={"prompt": 0, "completion": 0},
            error=str(last_error) if last_error else "Unknown provider error",
        )

    # ── Subclass hook ────────────────────────────────────────────

    @abstractmethod
    def _call_api(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> AIResponse:
        """Provider-specific API call. Must be implemented by subclasses.

        Should raise ProviderError subclasses on failure.
        """
        ...

    # ── Internals ────────────────────────────────────────────────

    def _call_with_timeout(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> AIResponse:
        """Wrap _call_api with timeout enforcement."""
        import threading

        result_container: Dict[str, Any] = {"response": None, "error": None}
        done = threading.Event()

        def _target():
            try:
                result_container["response"] = self._call_api(
                    system_prompt, user_prompt, model, temperature, max_tokens
                )
            except Exception as e:
                result_container["error"] = e
            finally:
                done.set()

        thread = threading.Thread(target=_target, daemon=True)
        thread.start()

        if not done.wait(timeout=self.config.timeout):
            raise ProviderError(
                f"Provider call timed out after {self.config.timeout}s",
                details={"timeout": self.config.timeout},
            )

        if result_container["error"]:
            err = result_container["error"]
            if isinstance(err, ProviderError):
                raise err
            raise ProviderError(str(err))

        return result_container["response"]

    # ── Stats ────────────────────────────────────────────────────

    @property
    def call_count(self) -> int:
        return self._call_count

    @property
    def total_tokens(self) -> int:
        return self._total_tokens

    @property
    def error_count(self) -> int:
        return self._error_count

    def get_stats(self) -> dict:
        return {
            "call_count": self._call_count,
            "total_tokens": self._total_tokens,
            "error_count": self._error_count,
            "config": self.config.safe_repr(),
        }

    def reset_stats(self):
        self._call_count = 0
        self._total_tokens = 0
        self._error_count = 0
