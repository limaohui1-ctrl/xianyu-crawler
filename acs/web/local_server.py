"""ACS Local Discovery Server — lightweight HTTP bridge from UI to discovery pipeline.

Start with:
  python -m acs.web.local_server [--port 5020]

Security: ACS_MODE=shadow enforced. No Cookie/Token/Authorization accepted.
No real search engine. No commercial platform access.
"""
import json
import os
import sys
import time
from flask import Flask, request, jsonify

app = Flask(__name__)

# ── Hard security gates ──
FORBIDDEN_HEADERS = {"cookie", "authorization", "x-api-key", "x-auth-token"}
ACS_MODE = "shadow"


def _security_check():
    """Reject requests carrying auth headers. Return (blocked, reason)."""
    for h in FORBIDDEN_HEADERS:
        if h in request.headers:
            return True, f"forbidden header: {h}"
    body_str = (request.data or b"").decode("utf-8", errors="replace").lower()
    for kw in ["authorization", "bearer ", "token=", "cookie=", "session="]:
        if kw in body_str:
            return True, f"forbidden body keyword: {kw}"
    return False, ""


# ── Health ──
@app.route("/api/health")
def health():
    return jsonify({
        "status": "ok",
        "acs_mode": ACS_MODE,
        "production_enabled": False,
        "server": "acs-local-discovery",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    })


# ── Discovery Run ──
@app.route("/api/discovery/run", methods=["POST"])
def discovery_run():
    blocked, reason = _security_check()
    if blocked:
        return jsonify({"error": reason}), 403

    data = request.get_json(silent=True) or {}
    provider = data.get("provider", "mock")
    topic = data.get("topic", "")
    keywords = data.get("keywords", [])
    limit = int(data.get("limit", 20))
    input_path = data.get("input_path", "")
    sitemap_url = data.get("sitemap_url", "")
    feed_url = data.get("feed_url", "")

    # Provider safety check
    if provider in ("search", "google", "bing", "serpapi", "serper"):
        return jsonify({"error": f"Provider '{provider}' not allowed. Real search engines disabled."}), 403

    from acs.discovery.source_discovery import SourceDiscovery
    sd = SourceDiscovery("acs_data/discovery")

    extra = {}
    if provider == "import-file":
        extra["input_path"] = input_path
        if not input_path:
            return jsonify({"error": "input_path required for import-file provider"}), 400
    elif provider == "sitemap":
        extra["sitemap_url"] = sitemap_url
        if not sitemap_url:
            return jsonify({"error": "sitemap_url required"}), 400
    elif provider == "rss":
        extra["feed_url"] = feed_url
        if not feed_url:
            return jsonify({"error": "feed_url required"}), 400

    try:
        result = sd.discover(
            topic=topic, keywords=keywords,
            provider=provider, limit=limit,
            auto_select_allowed=True,
            extra_params=extra,
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"discovery failed: {str(e)}"}), 500

    return jsonify({
        "batch_id": result["batch_id"],
        "total_candidates": result["report"]["total_candidates"],
        "allowed_count": result["report"]["allowed_count"],
        "needs_review_count": result["report"]["needs_review_count"],
        "blocked_count": result["report"]["blocked_count"],
        "candidates": result["candidates"],
        "selected_urls_path": result["selected_urls_path"],
        "query": {"topic": topic, "keywords": keywords, "provider": provider},
    })


# ── Candidate Select ──
@app.route("/api/discovery/select", methods=["POST"])
def discovery_select():
    blocked, reason = _security_check()
    if blocked:
        return jsonify({"error": reason}), 403

    data = request.get_json(silent=True) or {}
    batch_id = data.get("batch_id", "")
    selected_urls = data.get("selected_urls", [])

    if not batch_id:
        return jsonify({"error": "batch_id required"}), 400

    from acs.discovery.source_discovery import SourceDiscovery
    from acs.discovery.compliance_filter import ComplianceFilter

    sd = SourceDiscovery("acs_data/discovery")
    loaded = sd.load_batch(batch_id)
    if "error" in loaded:
        return jsonify({"error": loaded["error"]}), 404

    candidates = loaded["candidates"]
    from acs.discovery.candidate_url import CandidateUrl
    cf = ComplianceFilter()

    # Convert dicts to CandidateUrl objects, re-validate compliance
    selected_set = set(selected_urls)
    rejected = []
    cand_objs = []
    for c in candidates:
        obj = CandidateUrl.from_dict(c) if isinstance(c, dict) else c
        cf.evaluate(obj)
        cand_objs.append(obj)
        if obj.url in selected_set and obj.compliance_status == "blocked":
            rejected.append(obj.url)

    if rejected:
        return jsonify({
            "error": "blocked URLs cannot be selected",
            "rejected_urls": rejected,
        }), 403

    # Mark selected
    sd.store.mark_selected(cand_objs, selected_urls)

    # Export
    out_path = sd.store.export_selected_urls(cand_objs)
    selected_count = sum(1 for c in cand_objs if c.selected)

    return jsonify({
        "batch_id": batch_id,
        "selected_count": selected_count,
        "selected_urls_path": out_path,
    })


# ── Create Shadow Task ──
@app.route("/api/tasks/create-from-selected", methods=["POST"])
def task_create():
    blocked, reason = _security_check()
    if blocked:
        return jsonify({"error": reason}), 403

    data = request.get_json(silent=True) or {}
    batch_id = data.get("batch_id", "")

    selected_path = "acs_data/discovery/selected_urls.txt"
    if batch_id:
        from acs.discovery.source_discovery import SourceDiscovery
        sd = SourceDiscovery("acs_data/discovery")
        loaded = sd.load_batch(batch_id)
        if "error" not in loaded:
            from acs.discovery.candidate_url import CandidateUrl
            cands = [CandidateUrl.from_dict(c) for c in loaded["candidates"]]
            selected = [c for c in cands if c.selected]
            from acs.discovery.candidate_store import CandidateStore
            store = CandidateStore("acs_data/discovery")
            store.export_selected_urls(cands, selected_path)

    task_id = f"discovery_task_{int(time.time()*1000)}"
    cmd = (
        f"D:/Python312/python.exe -m acs.scripts.run_shadow_batch "
        f'--urls {selected_path} --site-id {task_id} '
        f"--max-urls 20 --rate-limit 0.3"
    )

    return jsonify({
        "task_id": task_id,
        "url_file": selected_path,
        "mode": "shadow",
        "command_preview": cmd,
        "acs_mode_on": False,
    })


# ── Main ──
def main():
    import argparse
    p = argparse.ArgumentParser(description="ACS Local Discovery Server")
    p.add_argument("--port", type=int, default=5020)
    p.add_argument("--host", default="127.0.0.1")
    args = p.parse_args()

    print(f"ACS Local Discovery Server starting on http://{args.host}:{args.port}")
    print(f"ACS_MODE={ACS_MODE}")
    print(f"CORS: static HTML from file:// allowed")

    @app.after_request
    def add_cors(response):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["X-ACS-Mode"] = ACS_MODE
        return response

    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
