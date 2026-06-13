"""
AI Parser — LLM-based field extraction as a last-resort fallback parser.

This parser is ALWAYS a fallback.  It is only invoked when:
  - All conventional parsers (CSS/XPath/JSON/JSONLD/fallback) have failed
  - Critical fields are missing
  - The AI parse policy explicitly allows it

Output is ALWAYS structured JSON — never free text.  Every field carries
a confidence score and evidence citation.

Usage:
    from acs.parser.ai_parser import AIParser
    from acs.strategy.ai_parse_policy import AIParsePolicy

    policy = AIParsePolicy(cost_controller=cc)
    parser = AIParser(policy=policy)

    # Only if policy allows:
    decision = policy.should_invoke_ai_parser(url=url, parse_result=result)
    if decision.should_invoke:
        ai_result = parser.parse(url, html, missing_fields=["title", "price"])
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
import json
import re
import time

from acs.core.result_model import ParseResult
from acs.fetcher.response_classifier import ContentType
from acs.parser.parser_engine import BaseParser
from acs.schema.field_mapper import FieldMapper, STANDARD_AI_FIELDS
from acs.strategy.ai_parse_policy import AIParsePolicy, AIParseDecision


# ── AI response types ────────────────────────────────────────────

@dataclass
class AIFieldResult:
    """Single field extracted by AI parser."""
    value: str = ""
    confidence: float = 0.0
    evidence: str = ""
    extracted: bool = False


@dataclass
class AIParseOutput:
    """Structured output from AI parser."""
    success: bool = False
    url: str = ""
    parser: str = "ai_parser"
    fields: Dict[str, AIFieldResult] = field(default_factory=dict)
    missing_fields: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    cost: Dict[str, Any] = field(default_factory=dict)
    raw_response: str = ""
    parse_error: str = ""

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "url": self.url,
            "parser": self.parser,
            "fields": {
                name: {
                    "value": f.value,
                    "confidence": f.confidence,
                    "evidence": f.evidence,
                }
                for name, f in self.fields.items()
            },
            "missing_fields": self.missing_fields,
            "warnings": self.warnings,
            "cost": self.cost,
        }


# ── AI Client interface (pluggable, mock-friendly) ───────────────

class AIClient:
    """Pluggable AI client — override for different providers (OpenAI, etc.).

    The default implementation is a NO-OP that returns a structured
    error response.  Real API integration is done via subclass.
    """

    def complete(self, system_prompt: str, user_prompt: str,
                 model: str = "", temperature: float = 0.3,
                 max_tokens: int = 2000) -> dict:
        """Call the AI model. Returns {"text": str, "tokens": {prompt, completion}}."""
        return {
            "text": "",
            "tokens": {"prompt": 0, "completion": 0},
            "error": "AIClient not configured — use subclass or mock",
        }


# ── AI Parser ────────────────────────────────────────────────────

class AIParser(BaseParser):
    """LLM-based field extraction parser — fallback only.

    Args:
        ai_client: Pluggable AI client (default: no-op AIClient)
        policy: AIParsePolicy for cost/usage control
        field_mapper: FieldMapper for building prompts and parsing responses
        min_confidence: Minimum field confidence to accept
        max_html_length: Truncate HTML to this length for the AI prompt
    """

    name = "ai_parser"

    def __init__(
        self,
        ai_client: Optional[AIClient] = None,
        policy: Optional[AIParsePolicy] = None,
        field_mapper: Optional[FieldMapper] = None,
        min_confidence: float = 0.5,
        max_html_length: int = 8000,
    ):
        self.ai_client = ai_client or AIClient()
        self.policy = policy or AIParsePolicy()
        self.field_mapper = field_mapper or FieldMapper()
        self.min_confidence = min_confidence
        self.max_html_length = max_html_length
        self._call_history: List[dict] = []

    # ── BaseParser interface ─────────────────────────────────────

    def can_handle(self, content_type: ContentType, body: str) -> bool:
        """AI parser can handle HTML and plain text (but is always a fallback)."""
        return content_type in (ContentType.HTML, ContentType.PLAIN_TEXT)

    def parse(self, url: str, body: str, **kwargs) -> ParseResult:
        """Parse using AI. Returns ParseResult with AI-extracted fields.

        Kwargs:
            missing_fields: List of field names to focus on
            force: If True, skip policy check (use with caution)
        """
        missing_fields = kwargs.get("missing_fields", [])
        force = kwargs.get("force", False)

        result = ParseResult(url=url, parser_used="ai_parser")

        # ── Policy check ──
        if not force:
            decision = self.policy.should_invoke_ai_parser(
                url=url,
                missing_critical_fields=missing_fields,
            )
            if not decision.should_invoke:
                result.error = f"AI parser blocked by policy: {decision.reason}"
                result.error_category = "parse_empty"
                result.build()
                return result

        # ── Build prompt ──
        prompt = self.field_mapper.build_prompt(
            html=body,
            missing_fields=missing_fields,
            max_html_length=self.max_html_length,
        )

        # ── Call AI ──
        t0 = time.time()
        ai_response = self.ai_client.complete(
            system_prompt="你是一个精确的网页数据提取助手。只返回JSON，不要额外文字。",
            user_prompt=prompt,
            temperature=0.3,
            max_tokens=2000,
        )
        elapsed = round(time.time() - t0, 3)

        # ── Record cost ──
        tokens = ai_response.get("tokens", {})
        self.policy.record_ai_call(
            url=url,
            prompt_tokens=tokens.get("prompt", 0),
            completion_tokens=tokens.get("completion", 0),
        )
        self._call_history.append({
            "url": url,
            "elapsed": elapsed,
            "tokens": tokens,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        })

        # ── Parse response ──
        response_text = ai_response.get("text", "")
        ai_error = ai_response.get("error", "")

        if ai_error and not response_text:
            result.error = f"AI client error: {ai_error}"
            result.error_category = "parse_general"
            result.build()
            return result

        # Parse structured fields
        parsed_fields = self.field_mapper.parse_ai_response(response_text)

        # Check if any fields were actually extracted
        any_extracted = any(f.get("extracted") for f in parsed_fields.values())
        if not any_extracted:
            result.warnings.append(type("ParseWarning", (), {
                "code": "AI_PARSE_EMPTY",
                "message": "AI returned no extractable fields",
                "field": "",
                "to_dict": lambda: {"code": "AI_PARSE_EMPTY", "message": "AI returned no extractable fields", "field": ""},
            })())
            result.error = "AI parser returned no extractable fields"
            result.error_category = "parse_empty"
            result.build()
            return result

        # ── Merge into result ──
        merge_info = self.field_mapper.merge_ai_result(
            result, parsed_fields,
            min_confidence=self.min_confidence,
        )
        result.metadata["ai_parser"] = {
            "elapsed_seconds": elapsed,
            "tokens": tokens,
            "merge_info": merge_info,
        }

        # ── Warning for low-confidence fields ──
        for low in merge_info.get("low_confidence_fields", []):
            result.warnings.append(type("ParseWarning", (), {
                "code": "LOW_CONFIDENCE",
                "message": f"Field '{low['field']}' has low confidence ({low['confidence']})",
                "field": low['field'],
                "to_dict": lambda l=low: {"code": "LOW_CONFIDENCE", "message": f"Field '{l['field']}' has low confidence ({l['confidence']})", "field": l['field']},
            })())

        result.build()
        return result

    # ── Direct AI extraction (raw output, no policy check) ───────

    def extract_raw(self, url: str, html: str,
                    missing_fields: Optional[List[str]] = None) -> AIParseOutput:
        """Extract fields and return structured AI output directly.

        Does NOT go through policy checks. Use only for testing/debugging.

        Returns AIParseOutput with full field details.
        """
        output = AIParseOutput(url=url, success=False)

        prompt = self.field_mapper.build_prompt(
            html=html,
            missing_fields=missing_fields,
            max_html_length=self.max_html_length,
        )

        t0 = time.time()
        ai_response = self.ai_client.complete(
            system_prompt="你是一个精确的网页数据提取助手。只返回JSON，不要额外文字。",
            user_prompt=prompt,
            temperature=0.3,
            max_tokens=2000,
        )
        elapsed = round(time.time() - t0, 3)

        tokens = ai_response.get("tokens", {})
        output.cost = {
            "prompt_tokens": tokens.get("prompt", 0),
            "completion_tokens": tokens.get("completion", 0),
            "estimated_cost": round(
                (tokens.get("prompt", 0) + tokens.get("completion", 0)) * 0.00001, 6
            ),
            "elapsed_seconds": elapsed,
        }

        response_text = ai_response.get("text", "")
        ai_error = ai_response.get("error", "")
        output.raw_response = response_text[:5000]

        if ai_error and not response_text:
            output.parse_error = f"AI client error: {ai_error}"
            return output

        parsed_fields = self.field_mapper.parse_ai_response(response_text)

        for field in STANDARD_AI_FIELDS:
            data = parsed_fields.get(field.name, {})
            output.fields[field.name] = AIFieldResult(
                value=str(data.get("value", "")),
                confidence=data.get("confidence", 0.0),
                evidence=str(data.get("evidence", ""))[:500],
                extracted=data.get("extracted", False),
            )

        # Detect missing fields
        for field in STANDARD_AI_FIELDS:
            if not output.fields[field.name].extracted:
                output.missing_fields.append(field.name)

        output.success = any(f.extracted for f in output.fields.values())
        return output

    # ── Call history ─────────────────────────────────────────────

    @property
    def call_count(self) -> int:
        return len(self._call_history)

    def get_call_history(self, limit: int = 50) -> List[dict]:
        return self._call_history[-limit:]
