"""
Parser engine — orchestrates multiple parsers for a single page.

Given an HTTP response (HTML, JSON, etc.), the engine:
  1. Classifies the content type
  2. Selects appropriate parsers (CSS, XPath, JSON, JSONLD, fallback)
  3. Runs parsers in priority order
  4. Merges results into a unified ParseResult
  5. Scores and returns the best result

Parsers can be registered dynamically.  Each parser implements:
    can_handle(content_type, body) -> bool
    parse(url, body, **kwargs) -> ParseResult
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Type
import time

from acs.core.result_model import ParseResult, ParseWarning
from acs.fetcher.response_classifier import (
    ContentType,
    ResponseClassification,
    classify_response,
)


# ── Parser interface ────────────────────────────────────────────

class BaseParser(ABC):
    """Abstract base for all parsers."""

    name: str = "base"

    @abstractmethod
    def can_handle(self, content_type: ContentType, body: str) -> bool:
        """Return True if this parser can process the given content."""
        ...

    @abstractmethod
    def parse(self, url: str, body: str, **kwargs) -> ParseResult:
        """Parse the response body into a ParseResult."""
        ...

    def __repr__(self) -> str:
        return f"<{self.name}>"


# ── Parser priority ─────────────────────────────────────────────

# Parsers are tried in this order.  Higher priority = tried first.
# The first parser that returns can_handle=True gets to parse.
PARSER_PRIORITY = [
    "jsonld",    # structured data is most authoritative
    "json",      # API responses
    "css",       # CSS selectors (most common)
    "xpath",     # XPath (backup for CSS)
    "fallback",  # always succeeds
]


def default_parser_order() -> List[str]:
    """Return the default parser evaluation order."""
    return list(PARSER_PRIORITY)


# ── Engine ──────────────────────────────────────────────────────

@dataclass
class ParseAttempt:
    """Record of one parser's attempt."""
    parser_name: str = ""
    handled: bool = False
    success: bool = False
    elapsed_ms: float = 0.0
    error: str = ""
    result: Optional[ParseResult] = None


class ParserEngine:
    """Orchestrates multiple parsers for a single URL.

    Usage:
        engine = ParserEngine()
        engine.register(CssParser())
        engine.register(XPathParser())
        engine.register(JsonLdParser())
        engine.register(FallbackParser())

        result, attempts = engine.parse("https://example.com", html_body)
    """

    def __init__(self, parser_order: Optional[List[str]] = None):
        self._parsers: Dict[str, BaseParser] = {}
        self._order: List[str] = parser_order or default_parser_order()

    # ── Registration ─────────────────────────────────────────

    def register(self, parser: BaseParser):
        """Register a parser.  The parser's .name determines its priority slot."""
        self._parsers[parser.name] = parser
        if parser.name not in self._order:
            self._order.append(parser.name)

    def unregister(self, name: str):
        """Remove a parser by name."""
        self._parsers.pop(name, None)
        if name in self._order:
            self._order.remove(name)

    def set_order(self, order: List[str]):
        """Override the parser evaluation order."""
        self._order = list(order)

    @property
    def registered_parsers(self) -> List[str]:
        return [p for p in self._order if p in self._parsers]

    # ── Parsing ──────────────────────────────────────────────

    def parse(
        self,
        url: str,
        body: str,
        http_status: int = 200,
        mime_type: str = "",
        force_parser: Optional[str] = None,
        **kwargs,
    ) -> tuple[ParseResult, List[ParseAttempt]]:
        """Parse a response body.

        Args:
            url: Source URL
            body: Response body text
            http_status: HTTP status code
            mime_type: Content-Type header
            force_parser: Override auto-selection — use this parser name
            **kwargs: Passed through to parsers

        Returns:
            (best_result, list_of_all_attempts)
        """
        attempts: List[ParseAttempt] = []

        # Classify the content
        classification = classify_response(
            url=url, body=body,
            http_status=http_status,
            mime_type=mime_type,
        )

        # If we should skip, return an empty result
        if classification.should_skip:
            result = ParseResult(
                url=url,
                parser_used="none",
                error=f"Response classified as unparseable: {classification.page_kind.value}",
                error_category=classification.page_kind.value,
            )
            return result, attempts

        # If forced, use that parser only
        if force_parser and force_parser in self._parsers:
            parser = self._parsers[force_parser]
            attempt = self._try_parser(parser, url, body, classification, **kwargs)
            attempts.append(attempt)
            if attempt.success and attempt.result:
                return attempt.result, attempts
            # Fall through to auto if forced parser failed

        # Auto-select: try parsers in priority order
        for name in self._order:
            parser = self._parsers.get(name)
            if parser is None:
                continue
            if not parser.can_handle(classification.content_type, body):
                attempts.append(ParseAttempt(
                    parser_name=name,
                    handled=False,
                ))
                continue
            attempt = self._try_parser(parser, url, body, classification, **kwargs)
            attempts.append(attempt)
            if attempt.success and attempt.result:
                return attempt.result, attempts

        # No parser succeeded — this shouldn't happen if fallback is registered
        result = ParseResult(
            url=url,
            parser_used="none",
            error="No parser could handle this content",
            error_category="parse_general",
        )
        return result, attempts

    def _try_parser(
        self,
        parser: BaseParser,
        url: str,
        body: str,
        classification: ResponseClassification,
        **kwargs,
    ) -> ParseAttempt:
        """Try one parser, catch and record any errors."""
        attempt = ParseAttempt(parser_name=parser.name)
        attempt.handled = True
        t0 = time.time()
        try:
            result = parser.parse(url, body, **kwargs)
            attempt.elapsed_ms = round((time.time() - t0) * 1000, 1)
            # Only mark success if the parser actually produced data
            # A parser that returns with an error but no useful content did NOT succeed
            if result and result.parser_used and not result.error:
                attempt.result = result
                attempt.success = True
            elif result and result.parser_used:
                # Parser ran but reported an error — record it, don't mark as success
                attempt.error = result.error or "Parser returned empty result"
                attempt.result = result  # keep for inspection
            else:
                attempt.error = "Parser returned empty result"
        except Exception as exc:
            attempt.elapsed_ms = round((time.time() - t0) * 1000, 1)
            attempt.error = str(exc)[:500]
        return attempt

    # ── Convenience ──────────────────────────────────────────

    @classmethod
    def create_default(cls) -> "ParserEngine":
        """Create an engine with the standard parser set.

        Import order matters — parsers are imported lazily to avoid
        circular dependencies.
        """
        from acs.parser.css_parser import CssParser
        from acs.parser.xpath_parser import XPathParser
        from acs.parser.json_parser import JsonParser
        from acs.parser.jsonld_parser import JsonLdParser
        from acs.parser.fallback_parser import FallbackParser

        engine = cls()
        engine.register(CssParser())
        engine.register(XPathParser())
        engine.register(JsonParser())
        engine.register(JsonLdParser())
        engine.register(FallbackParser())
        return engine
