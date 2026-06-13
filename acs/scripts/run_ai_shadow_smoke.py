#!/usr/bin/env python
"""
CLI entry point for AI shadow smoke test.

Usage:
    python -m acs.scripts.run_ai_shadow_smoke --url https://example.com --max-ai-calls 1

This script requires valid AI provider environment variables:
    AI_BASE_URL, AI_API_KEY, AI_MODEL, AI_PARSER_ENABLED=true

It does NOT run during pytest.  It is a standalone smoke test.
"""

import argparse
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def main():
    parser = argparse.ArgumentParser(
        description="ACS AI Shadow Smoke Test — verify real AI provider integration"
    )
    parser.add_argument("--url", default="https://example.com",
                        help="URL to test parse (default: https://example.com)")
    parser.add_argument("--html", default="",
                        help="Inline HTML to parse (overrides --url fetch)")
    parser.add_argument("--max-ai-calls", type=int, default=1,
                        help="Max AI calls for this run (default: 1)")
    parser.add_argument("--max-cost", type=float, default=0.50,
                        help="Max cost for this run (default: 0.50)")
    parser.add_argument("--raw", action="store_true",
                        help="Run in raw mode (no policy checks)")
    parser.add_argument("--json", dest="json_output", action="store_true",
                        help="Output as JSON (default: human-readable)")

    args = parser.parse_args()

    # ── Check environment ──
    from acs.provider.provider_config import ProviderConfig
    config = ProviderConfig.from_env()

    if not config.is_configured():
        print(json.dumps({
            "success": False,
            "error": "Not configured.",
            "help": "Set AI_BASE_URL, AI_API_KEY, AI_MODEL, AI_PARSER_ENABLED=true",
            "config": config.safe_repr(),
        }, ensure_ascii=False, indent=2))
        sys.exit(1)

    # ── Run smoke ──
    if args.raw:
        from acs.provider.live_ai_smoke import run_smoke_raw
        result = run_smoke_raw(url=args.url, html=args.html)
    else:
        from acs.provider.live_ai_smoke import run_smoke
        result = run_smoke(
            url=args.url, html=args.html,
            max_ai_calls=args.max_ai_calls,
            max_cost=args.max_cost,
        )

    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        print("=" * 60)
        print("ACS AI Shadow Smoke Test Results")
        print("=" * 60)
        print(f"URL: {args.url}")
        print(f"Success: {result.get('success', False)}")
        print(f"API key configured: {result.get('api_key_present', False)}")
        print(f"API key in logs: {result.get('api_key_in_logs', True)} ⚠️" if result.get('api_key_in_logs') else "API key in logs: False ✅")
        print()

        ai = result.get("ai_result", {})
        if ai:
            print("AI Parse Result:")
            for k, v in ai.items():
                print(f"  {k}: {str(v)[:100]}")

        summary = result.get("summary", {})
        if summary:
            print()
            print("Cost Summary:")
            for k, v in summary.items():
                print(f"  {k}: {v}")

        errors = result.get("errors", [])
        if errors:
            print()
            print("Errors:")
            for e in errors:
                print(f"  - {e}")

        print()
        print("Logs written to:")
        print("  logs/ai_call_audit.jsonl")
        print("  logs/ai_cost_report.json")

    sys.exit(0 if result.get("success") else 1)


if __name__ == "__main__":
    main()
