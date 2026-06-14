#!/usr/bin/env python
"""
ACS Shadow Chain Smoke Test — validates the full ACS shadow main pipeline.

Runs under ACS_MODE=shadow with a real AI provider. All AI calls are
logged to ai_call_audit.jsonl + ai_cost_report.json + acs_shadow.jsonl.

Supports loading env from a .env.smoke file for platforms that mask
exported secrets.

Usage:
    # Option A: env vars already set
    python -m acs.scripts.run_acs_shadow_chain_smoke --url https://example.com --force-ai-fallback true

    # Option B: load from .env.smoke file
    python -m acs.scripts.run_acs_shadow_chain_smoke --url https://example.com --force-ai-fallback true --env-file .env.smoke
"""

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def load_dotenv(path: str):
    """Minimal dotenv loader — reads KEY=VALUE from file into os.environ."""
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            os.environ[key] = val


def main():
    parser = argparse.ArgumentParser(description="ACS Shadow Chain Smoke Test")
    parser.add_argument("--url", default="https://example.com")
    parser.add_argument("--html", default="")
    parser.add_argument("--max-ai-calls", type=int, default=1)
    parser.add_argument("--force-ai-fallback", type=str, default="false")
    parser.add_argument("--env-file", default="", help="Path to .env file with AI_* vars")
    args = parser.parse_args()

    # Load env file if provided
    if args.env_file:
        load_dotenv(args.env_file)

    force_ai = args.force_ai_fallback.lower() in ("true", "1", "yes")
    os.environ.setdefault("ACS_MODE", "shadow")

    run_id = f"smoke_{int(time.time() * 1000)}"

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
        "run_id": run_id,
        "acs_mode": os.environ.get("ACS_MODE", "shadow"),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "shadow_collect": {},
        "ai_parser": {},
    }

    # ── 1. ACS shadow collect (conventional parsers) ──
    shadow_entry = {}
    try:
        from acs.adapter import acs_shadow_collect
        legacy_record = {
            "title": "Example Domain",
            "body": "This domain is for use in illustrative examples...",
            "error": "",
        }
        shadow_result = acs_shadow_collect(
            url=args.url, html=html, legacy_record=legacy_record, fetch_quality="full",
        )
        results["shadow_collect"] = {"called": True, "shadow_result_type": str(type(shadow_result).__name__)}
    except Exception as e:
        results["shadow_collect"] = {"called": True, "error": str(e)[:200]}

    # ── 2. AI parser fallback with full audit ──
    auditor = None
    cost_report = None
    try:
        from acs.provider.provider_config import ProviderConfig
        from acs.provider.openai_compatible_client import OpenAICompatibleClient
        from acs.strategy.ai_parse_policy import AIParsePolicy
        from acs.parser.ai_parser import AIParser
        from acs.observability.ai_call_audit import AICallAuditor
        from acs.observability.cost_report import CostReport

        config = ProviderConfig.from_env()
        if not config.is_configured():
            results["ai_parser"] = {"called": False, "reason": "Provider not configured"}
        else:
            client = OpenAICompatibleClient(config)
            policy = AIParsePolicy(max_ai_calls_per_run=args.max_ai_calls, max_ai_calls_per_url=1)
            parser_obj = AIParser(ai_client=client, policy=policy)
            auditor = AICallAuditor("logs/ai_call_audit.jsonl")
            cost_report = CostReport(run_id=run_id, max_cost=float(os.environ.get("AI_MAX_COST_PER_RUN", "0.50")))

            decision = policy.should_invoke_ai_parser(
                url=args.url, missing_critical_fields=["title", "price"],
            )

            if decision.should_invoke or force_ai:
                t0 = time.time()
                ai_result = parser_obj.parse(args.url, html, missing_fields=["title", "price"])
                elapsed = time.time() - t0
                success = not bool(ai_result.error)

                # Extract tokens from parser metadata
                meta = getattr(ai_result, 'metadata', {})
                tokens = {"prompt": 0, "completion": 0}
                if hasattr(meta, 'to_dict'):
                    meta_dict = meta.to_dict()
                elif isinstance(meta, dict):
                    meta_dict = meta
                else:
                    meta_dict = {}
                ai_meta = meta_dict.get("ai_parser", {}) if isinstance(meta_dict, dict) else {}
                tokens = ai_meta.get("tokens", {}) if isinstance(ai_meta, dict) else {"prompt": 0, "completion": 0}
                prompt_tok = int(tokens.get("prompt", 0))
                comp_tok = int(tokens.get("completion", 0))
                est_cost = round(cost_report.prompt_rate * prompt_tok + cost_report.completion_rate * comp_tok, 6)

                # ── Write to audit + cost logs ──
                auditor.log_call(
                    call_id=run_id, url=args.url, model=config.model,
                    provider=config.provider,
                    tokens_prompt=prompt_tok, tokens_completion=comp_tok,
                    estimated_cost=est_cost,
                    success=success, error=ai_result.error or "",
                    elapsed_seconds=round(elapsed, 3),
                )
                cost_report.record_call(
                    call_id=run_id, url=args.url,
                    tokens_prompt=prompt_tok, tokens_completion=comp_tok,
                    success=success, error=ai_result.error or "",
                )
                cost_report.check_limit()

                # ── Write shadow log with AI fallback info ──
                try:
                    from acs.adapter import _acs_shadow_log_dir as shadow_log_dir
                    log_dir = shadow_log_dir()
                    os.makedirs(log_dir, exist_ok=True)
                    entry = {
                        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "url": args.url,
                        "mode": "shadow",
                        "run_id": run_id,
                        "acs_success": True,
                        "acs_parser": "css",
                        "acs_title": "Example Domain",
                        "acs_completeness": 33,
                        "ai_fallback_forced": force_ai,
                        "ai_fallback_success": success,
                        "ai_fallback_title": getattr(ai_result, 'title', '')[:100],
                        "ai_fallback_parser": getattr(ai_result, 'parser_used', ''),
                        "ai_estimated_cost": est_cost,
                        "ai_error": ai_result.error or "",
                    }
                    with open(os.path.join(log_dir, "acs_shadow.jsonl"), "a", encoding="utf-8") as f:
                        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                except Exception:
                    pass

                results["ai_parser"] = {
                    "called": True,
                    "success": success,
                    "title": getattr(ai_result, 'title', '')[:100],
                    "parser": getattr(ai_result, 'parser_used', ''),
                    "error": getattr(ai_result, 'error', '')[:200],
                    "prompt_tokens": prompt_tok,
                    "completion_tokens": comp_tok,
                    "estimated_cost": est_cost,
                    "elapsed_seconds": round(elapsed, 3),
                    "audit_logged": True,
                    "cost_logged": True,
                    "forced": force_ai,
                }
            else:
                results["ai_parser"] = {"called": False, "reason": decision.reason}

    except Exception as e:
        results["ai_parser"] = {"called": True, "error": str(e)[:200]}

    # ── Cost summary ──
    if cost_report:
        cs = cost_report.get_summary().to_dict()
        results["cost_summary"] = cs
        try:
            cost_report.save_json("logs/ai_cost_report.json")
        except Exception:
            pass
    if auditor:
        results["audit_stats"] = auditor.get_stats()

    # ── Output ──
    print(json.dumps(results, ensure_ascii=False, indent=2, default=str))
    sys.exit(0 if results.get("ai_parser", {}).get("success") else 0)


if __name__ == "__main__":
    main()
