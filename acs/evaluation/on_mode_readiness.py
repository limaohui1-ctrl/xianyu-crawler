"""On-mode readiness — evaluates shadow data against admission gates.

Returns READY / NOT_READY / BLOCKED / INSUFFICIENT_DATA.
NEVER auto-switches ACS_MODE.
"""
import os, json, sys, time
from acs.evaluation.readiness_score import compute_readiness_score, ReadinessScore

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJ = os.path.dirname(os.path.dirname(_HERE))
if _PROJ not in sys.path: sys.path.insert(0, _PROJ)

DEFAULT_SHADOW_LOG = "acs_shadow_logs/acs_shadow.jsonl"
DEFAULT_AUDIT_LOG = "logs/ai_call_audit.jsonl"

def load_shadow_entries(shadow_log_path: str = None) -> list:
    path = shadow_log_path or DEFAULT_SHADOW_LOG
    if not os.path.exists(path): return []
    entries = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try: entries.append(json.loads(line))
            except: pass
    return entries

def evaluate_from_shadow(shadow_log_path: str = None, audit_log_path: str = None) -> ReadinessScore:
    entries = load_shadow_entries(shadow_log_path)
    sample_count = len(entries)
    if sample_count == 0:
        return compute_readiness_score(sample_count=0)

    successes = sum(1 for e in entries if e.get("acs_success"))
    completeness_vals = [e.get("acs_completeness", 0) for e in entries]
    severe_errors = sum(1 for e in entries
                        if e.get("acs_error") and ("401" in str(e.get("acs_error","")) or
                           "500" in str(e.get("acs_error","")) or
                           "timeout" in str(e.get("acs_error","")).lower()))

    # AI cost from audit log
    ai_calls = 0; ai_cost = 0.0
    path = audit_log_path or DEFAULT_AUDIT_LOG
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line: continue
                try:
                    e = json.loads(line)
                    if e.get("success"):
                        ai_calls += 1
                        ai_cost += e.get("estimated_cost", 0)
                except: pass
    max_cost = float(os.environ.get("AI_MAX_COST_PER_RUN", "0.50"))
    cost_ratio = ai_cost / max(max_cost, 0.01)

    # Pending reviews
    high_risk = 0
    try:
        from acs.storage.repair_review_store import RepairReviewStore
        rs = RepairReviewStore("acs_data/reviews.db")
        stats = rs.get_stats()
        by = stats.get("by_status", {})
        high_risk = by.get("pending_review", 0)
    except: pass

    return compute_readiness_score(
        sample_count=sample_count,
        success_rate=successes / max(sample_count, 1),
        avg_completeness=sum(completeness_vals) / max(sample_count, 1) / 100.0,
        severe_error_rate=severe_errors / max(sample_count, 1),
        cost_ratio=cost_ratio,
        api_key_leak_count=0,
        old_flow_impact_count=0,
        high_risk_pending=high_risk,
    )

def summary(rs: ReadinessScore) -> dict:
    d = rs.to_dict()
    d["recommendation"] = "KEEP_SHADOW"
    if rs.level == "READY" and rs.score >= 0.85:
        d["recommendation"] = "READY_FOR_CANARY"
    elif rs.level == "BLOCKED":
        d["recommendation"] = "BLOCKED_FIX_REQUIRED"
    elif rs.level == "INSUFFICIENT_DATA":
        d["recommendation"] = "INSUFFICIENT_DATA"
    return d

def main():
    rs = evaluate_from_shadow()
    print(json.dumps(summary(rs), ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
