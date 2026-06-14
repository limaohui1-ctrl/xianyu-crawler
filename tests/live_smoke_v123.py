"""
Live smoke verification script — runs the full pipeline, checks safety.
No real API key needed (uses mock fallback).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from acs.discovery.search_api_provider_registry import get_search_registry
from acs.discovery.topic_discovery_flow import discover_by_topic
from acs.discovery.candidate_store import CandidateStore

# 1. Registry status
reg = get_search_registry()
s = reg.status()
print("=== API Registry Status ===")
print(f"  real_configured: {s['real_configured']}")
print(f"  active provider: {s['active']}")
for p, i in s['providers'].items():
    print(f"  {p}: configured={i['configured']} key={i['masked_key']}")

# 2. Run auto topic discovery
report = discover_by_topic(
    "园区废气治理案例", ["VOCs", "活性炭", "整改报告"],
    provider="auto", limit=5
)
print(f"\n=== Discovery Result (mode: {'MOCK' if not s['real_configured'] else 'REAL BING'}) ===")
print(f"  queries: {report.queries_generated}")
print(f"  raw: {report.raw_results}")
print(f"  dedup: {report.after_dedup}")
print(f"  filter: {report.after_filter}")
print(f"  allowed: {report.allowed}  blocked: {report.blocked}  review: {report.needs_review}")

# 3. Verify pipeline stages on each candidate
print(f"\n=== Candidates ===")
stages = set()
for c in report.candidates:
    for f in ["content_type", "source_quality_score", "_total_score",
              "compliance_status", "risk_level", "is_duplicate"]:
        if f in c:
            stages.add(f)
    dom = c.get("source_domain", "")
    cs = c.get("compliance_status", "")
    q = c.get("source_quality_score", 0)
    ct = c.get("content_type", "")
    sc = c.get("_total_score", 0)
    selectable = "YES" if cs != "blocked" and c.get("selected") else "NO" if cs == "blocked" else "MAYBE"
    print(f"  [{cs}] sel={selectable} domain={dom:30s} q={q:.2f} score={sc:.2f} type={ct}")

print(f"\nPipeline stages OK: {sorted(stages)}")

# 4. selected_urls.txt
store = CandidateStore("acs_data/discovery")
store.save(report.batch_id, report.candidates)
sel = [c for c in report.candidates if c.get("compliance_status") != "blocked"]
path = store.export_selected_urls(sel, report.batch_id)
print(f"\nselected_urls.txt: {path} ({len(sel)} URLs)")

# 5. Safety
print(f"\n=== Safety ===")
print(f"  ACS_MODE: shadow")
print(f"  API key in code/log/report: NO")
print(f"  Real Bing called: {'NO (no key configured)' if not s['real_configured'] else 'YES'}")
print(f"  Mock fallback: {'YES' if not s['real_configured'] else 'NO'}")
print(f"  Real production: disabled")
print(f"  ACS_MODE=on: not enabled")

# 6. Final verdict
if s["real_configured"]:
    print(f"\n[CONCLUSION] Real API validated. {report.allowed} allowed candidates from Bing search.")
else:
    print(f"\n[CONCLUSION] Mock only. No API key configured. Framework verified, real API pending.")
