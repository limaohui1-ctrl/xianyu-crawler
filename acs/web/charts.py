"""Chart data API — readonly JSON endpoints for Chart.js."""
import os, json, time
from flask import jsonify

def shadow_trend_data():
    entries = []
    path = "acs_shadow_logs/acs_shadow.jsonl"
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line: continue
                try: entries.append(json.loads(line))
                except Exception:  # skip malformed JSON lines
                    pass
    labels = [e.get("ts", "")[:16] for e in entries[-30:]]
    success = [1 if e.get("acs_success") else 0 for e in entries[-30:]]
    completeness = [e.get("acs_completeness", 0) for e in entries[-30:]]
    return jsonify({"labels": labels, "success": success, "completeness": completeness})

def ai_call_trend_data():
    entries = []
    path = "logs/ai_call_audit.jsonl"
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line: continue
                try: entries.append(json.loads(line))
                except Exception:  # skip malformed JSON lines
                    pass
    labels = [e.get("timestamp", "")[:16] for e in entries[-30:]]
    tokens = [e.get("tokens_prompt", 0) + e.get("tokens_completion", 0) for e in entries[-30:]]
    cost = [e.get("estimated_cost", 0) for e in entries[-30:]]
    success = [1 if e.get("success") else 0 for e in entries[-30:]]
    return jsonify({"labels": labels, "tokens": tokens, "cost": cost, "success": success})

def parser_distribution_data():
    entries = []
    path = "acs_shadow_logs/acs_shadow.jsonl"
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line: continue
                try: entries.append(json.loads(line))
                except Exception:  # skip malformed JSON lines
                    pass
    dist = {}
    for e in entries:
        p = e.get("acs_parser", "unknown")
        dist[p] = dist.get(p, 0) + 1
    return jsonify({"labels": list(dist.keys()), "values": list(dist.values())})

def review_status_data():
    try:
        from acs.storage.repair_review_store import RepairReviewStore
        s = RepairReviewStore("acs_data/reviews.db")
        stats = s.get_stats()
        by = stats.get("by_status", {})
        return jsonify({"labels": list(by.keys()), "values": list(by.values())})
    except:
        return jsonify({"labels": [], "values": []})

def structure_trend_data():
    try:
        from acs.storage.structure_history_store import StructureHistoryStore
        s = StructureHistoryStore("acs_data/structure_history.db")
        rows = s.get_recent("", limit=30)
        labels = [r.get("captured_at", "")[:16] for r in rows]
        scores = [r.get("change_score", 0) for r in rows]
        return jsonify({"labels": labels, "scores": scores})
    except:
        return jsonify({"labels": [], "scores": []})
