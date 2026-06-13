#!/usr/bin/env python
"""
ACS Shadow Chain Smoke Test — validates the full ACS shadow main pipeline.

Runs under ACS_MODE=shadow with a real AI provider:
  1. Calls acs_shadow_collect() → writes logs/acs_shadow.jsonl
  2. Triggers AI parser as fallback via AIParsePolicy → writes audit + cost logs
  3. Legacy output stays untouched

Requires: AI_BASE_URL, AI_API_KEY, AI_MODEL, AI_PARSER_ENABLED=true env vars.

Usage (from terminal):
    export AI_PARSER_ENABLED=true AI_BASE_URL=... AI_API_KEY=... AI_MODEL=... ACS_MODE=shadow
    python -m acs.scripts.run_acs_shadow_chain_smoke --url https://example.com
"""

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def main():
    parser = argparse.ArgumentParser(description="ACS Shadow Chain Smoke Test")
    parser.add_argument("--url", default="https://example.com")
    parser.add_argument("--html", default="")
    parser.add_argument("--max-ai-calls", type=int, default=1)
    parser.add_argument("--force-ai-fallback", type=str, default="false")
    args = parser.parse_args()
    force_ai = args.force_ai_fallback.lower() in ("true", "1", "yes")

    # Ensure ACS_MODE=shadow
    os.environ.setdefault("ACS_MODE", "shadow")

    # Fetch HTML if not provided
    html = args.html
    if not html:
        try:
            import urllib.request
            with urllib.request.urlopen(args.url, timeout=15) as resp:
                html = resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            print(json.dumps({"error": f"Failed to fetch URL: {e}"}, ensure_ascii=False))
            sys.exit(1)

    results = {
        "url": args.url,
        "acs_mode": os.environ.get("ACS_MODE", "shadow"),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "shadow_collect": {},
        "ai_parser": {},
    }

    # ── 1. ACS shadow collect (conventional parsers) ──
    try:
        from acs.adapter import acs_shadow_collect
        legacy_record = {
            "title": "Example Domain",
            "body": "This domain is for use in illustrative examples...",
            "error": "",
        }
        shadow_result = acs_shadow_collect(
            url=args.url,
            html=html,
            legacy_record=legacy_record,
            fetch_quality="full",
        )
        results["shadow_collect"] = {
            "called": True,
            "shadow_result_type": str(type(shadow_result).__name__),
        }
    except Exception as e:
        results["shadow_collect"] = {"called": True, "error": str(e)[:200]}

    # ── 2. AI parser fallback (shadow mode, policy-gated) ──
    try:
        from acs.provider.provider_config import ProviderConfig
        from acs.provider.openai_compatible_client import OpenAICompatibleClient
        from acs.strategy.ai_parse_policy import AIParsePolicy
        from acs.parser.ai_parser import AIParser

        config = ProviderConfig.from_env()
        if config.is_configured():
            client = OpenAICompatibleClient(config)
            policy = AIParsePolicy(max_ai_calls_per_run=args.max_ai_calls,
                                   max_ai_calls_per_url=1)
            parser_obj = AIParser(ai_client=client, policy=policy)

            decision = policy.should_invoke_ai_parser(
                url=args.url,
                missing_critical_fields=["title", "price"],
            )

            if decision.should_invoke or force_ai:
                if force_ai and not decision.should_invoke:
                    results["ai_parser"]["forced"] = True
                ai_result = parser_obj.parse(args.url, html,
                                             missing_fields=["title", "price"])
                results["ai_parser"] = {
                    "called": True,
                    "success": not bool(ai_result.error),
                    "title": getattr(ai_result, 'title', '')[:100],
                    "parser": getattr(ai_result, 'parser_used', ''),
                    "error": getattr(ai_result, 'error', '')[:200],
                }
            else:
                results["ai_parser"] = {
                    "called": False,
                    "reason": decision.reason,
                }
        else:
            results["ai_parser"] = {"called": False, "reason": "Provider not configured"}
    except Exception as e:
        results["ai_parser"] = {"called": True, "error": str(e)[:200]}

    # ── Output ──
    print(json.dumps(results, ensure_ascii=False, indent=2, default=str))

    # ── Check log files ──
    print()
    for log_name in ["acs_shadow_logs/acs_shadow.jsonl",
                     "logs/ai_call_audit.jsonl",
                     "logs/ai_cost_report.json"]:
        if os.path.exists(log_name):
            size = os.path.getsize(log_name)
            print(f"[EXISTS] {log_name} ({size} bytes)")
        else:
            print(f"[MISSING] {log_name}")


if __name__ == "__main__":
    main()
