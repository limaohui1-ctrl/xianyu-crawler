"""
Live AI Smoke Test — runs a real AI Provider call in shadow mode.

This is a standalone module, NOT part of pytest.  It requires
valid AI_BASE_URL / AI_API_KEY / AI_MODEL environment variables.

Usage:
    python -m acs.scripts.run_ai_shadow_smoke --url https://example.com --max-ai-calls 1

Environment (REQUIRED for real calls):
    AI_BASE_URL=https://api.openai.com/v1
    AI_API_KEY=***
    AI_MODEL=gpt-4o-mini
    AI_PARSER_ENABLED=true
"""

from acs.provider.provider_config import ProviderConfig
from acs.provider.openai_compatible_client import OpenAICompatibleClient
from acs.provider.provider_errors import ProviderError
from acs.schema.field_mapper import FieldMapper
from acs.strategy.ai_parse_policy import AIParsePolicy
from acs.parser.ai_parser import AIParser
from acs.observability.ai_call_audit import AICallAuditor
from acs.observability.cost_report import CostReport
import json


def run_smoke(
    url: str,
    html: str = "",
    max_ai_calls: int = 1,
    max_cost: float = 0.50,
) -> dict:
    """Run a single AI shadow smoke test.

    Args:
        url: Target URL
        html: HTML content to parse (if empty, fetches from url)
        max_ai_calls: Max AI calls for this smoke run
        max_cost: Max cost for this run

    Returns:
        Dict with results: {success, summary, audit, errors}
    """
    errors = []
    results = {"success": False, "summary": {}, "audit": {}, "errors": errors,
               "api_key_present": False, "api_key_in_logs": False}

    # ── 1. Load config ──
    config = ProviderConfig.from_env()
    results["api_key_present"] = bool(config.api_key)
    results["config"] = config.safe_repr()

    if not config.is_configured():
        errors.append("Not configured — set AI_BASE_URL, AI_API_KEY, AI_MODEL")
        return results

    # ── 2. Initialize components ──
    auditor = AICallAuditor("logs/ai_call_audit.jsonl")
    report = CostReport(run_id="smoke_test", max_cost=max_cost)

    client = OpenAICompatibleClient(config)
    if not html:
        try:
            import urllib.request
            with urllib.request.urlopen(url, timeout=15) as resp:
                html = resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            errors.append(f"Failed to fetch URL: {e}")
            return results

    policy = AIParsePolicy(max_ai_calls_per_run=max_ai_calls, max_ai_calls_per_url=1)
    parser = AIParser(ai_client=client, policy=policy)

    # ── 3. Invoke AI parser ──
    import time
    t0 = time.time()

    try:
        result = parser.parse(url, html, missing_fields=["title", "price"])
        elapsed = time.time() - t0

        if result.error:
            errors.append(f"AI parse error: {result.error}")
        else:
            results["ai_result"] = {
                "title": getattr(result, 'title', ''),
                "price": getattr(result, 'price', ''),
                "completeness": getattr(result, 'completeness', 0),
                "parser": getattr(result, 'parser_used', 'ai_parser'),
            }

        # Record to audit + cost report
        meta = getattr(result, 'metadata', {})
        ai_meta = meta.get("ai_parser", {}) if isinstance(meta, dict) else {}
        tokens = ai_meta.get("tokens", {})
        auditor.log_call(
            call_id=f"smoke_{int(time.time()*1000)}",
            url=url, model=config.model,
            tokens_prompt=tokens.get("prompt", 0),
            tokens_completion=tokens.get("completion", 0),
            estimated_cost=report.prompt_rate * tokens.get("prompt", 0) +
                          report.completion_rate * tokens.get("completion", 0),
            success=not bool(result.error),
            error=result.error or "",
            elapsed_seconds=elapsed,
        )

        report.record_call(
            url=url,
            tokens_prompt=tokens.get("prompt", 0),
            tokens_completion=tokens.get("completion", 0),
            success=not bool(result.error),
            error=result.error or "",
        )
        report.check_limit()

        results["success"] = not bool(result.error)
        results["summary"] = report.get_summary().to_dict()
        results["audit"] = auditor.get_stats()

    except ProviderError as e:
        errors.append(f"Provider error: {e}")
        report.record_call(url=url, success=False, error=str(e))
    except Exception as e:
        errors.append(f"Unexpected error: {e}")
        report.record_call(url=url, success=False, error=str(e))

    # ── 4. Safety check: API key not in logs ──
    log_entries = auditor.read_logs(limit=10)
    log_text = json.dumps(log_entries) if log_entries else ""
    results["api_key_in_logs"] = bool(config.api_key and config.api_key in log_text)

    # ── 5. Save reports ──
    try:
        report.save_json("logs/ai_cost_report.json")
    except OSError:
        pass

    return results


def run_smoke_raw(
    url: str,
    html: str = "",
) -> dict:
    """Run AI parser in raw mode (no policy checks). For debugging."""
    config = ProviderConfig.from_env()
    if not config.is_configured():
        return {"success": False, "error": "Not configured"}

    client = OpenAICompatibleClient(config)
    parser = AIParser(ai_client=client)

    output = parser.extract_raw(url, html)
    return output.to_dict()
