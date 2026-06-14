"""ACS Local Discovery Server — lightweight HTTP bridge from UI to discovery pipeline.

Start with:
  python -m acs.web.local_server [--port 5020]

Security: ACS_MODE=shadow enforced. No Cookie/Token/Authorization accepted.
No real search engine. No commercial platform access.
"""
import json
import os
import subprocess
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
    elif provider == "auto-domain":
        domain_url = data.get("domain_url", "")
        if not domain_url:
            return jsonify({"error": "domain_url required for auto-domain provider"}), 400
        extra["domain_url"] = domain_url
        extra["enable_robots"] = data.get("enable_robots", True)
        extra["enable_sitemap"] = data.get("enable_sitemap", True)
        extra["enable_rss"] = data.get("enable_rss", True)
        extra["enable_entry"] = data.get("enable_entry", True)
    elif provider == "topic-search":
        extra["content_type"] = data.get("content_type", "")
        extra["prefer_gov_edu"] = data.get("prefer_gov_edu", True)

    try:
        if provider == "auto-domain":
            from acs.discovery.domain_profile import discover_domain
            from acs.discovery.compliance_filter import ComplianceFilter
            from acs.discovery.relevance_ranker import RelevanceRanker
            from acs.discovery.candidate_url import CandidateUrl
            from acs.discovery.url_normalizer import dedup_urls
            profile = discover_domain(
                domain_url,
                topic=topic,
                max_candidates=limit,
                enable_robots=extra.get("enable_robots", True),
                enable_sitemap=extra.get("enable_sitemap", True),
                enable_rss=extra.get("enable_rss", True),
                enable_site_entry=extra.get("enable_entry", True),
            )
            if profile.error:
                return jsonify({"error": profile.error}), 400

            # Apply compliance + relevance
            cf = ComplianceFilter()
            rr = RelevanceRanker()
            all_cands = profile.robots_candidates + profile.sitemap_candidates + profile.feed_candidates + profile.site_entries
            for c in all_cands:
                obj = CandidateUrl.from_dict(c)
                cf.evaluate(obj)
                c.update(obj.to_dict())
            all_cands = rr.rank(all_cands, topic, keywords)
            all_cands = dedup_urls(all_cands, url_key="url")

            allowed = sum(1 for c in all_cands if c.get("compliance_status") == "allowed")
            review = sum(1 for c in all_cands if c.get("compliance_status") == "needs_review")
            blocked = sum(1 for c in all_cands if c.get("compliance_status") == "blocked")

            batch_id = f"ad_{profile.domain}_{int(time.time())}"
            return jsonify({
                "batch_id": batch_id,
                "total_candidates": len(all_cands),
                "allowed_count": allowed,
                "needs_review_count": review,
                "blocked_count": blocked,
                "candidates": all_cands,
                "domain": profile.domain,
                "robots_sitemaps": profile.robots_sitemaps,
                "sitemaps_found": len(profile.sitemap_urls_discovered),
                "feeds_found": len(profile.feed_urls_discovered),
                "entries_found": len(profile.site_entries),
                "query": {"topic": topic, "keywords": keywords, "provider": "auto-domain", "domain": profile.domain},
            })

        if provider == "topic-search":
            from acs.discovery.topic_discovery_flow import discover_by_topic
            report = discover_by_topic(
                topic=topic,
                keywords=keywords,
                content_type=extra.get("content_type", ""),
                limit=limit,
                provider="mock",
                prefer_gov_edu=extra.get("prefer_gov_edu", True),
            )
            return jsonify({
                "batch_id": report.batch_id,
                "total_candidates": report.after_filter,
                "allowed_count": report.allowed,
                "needs_review_count": report.needs_review,
                "blocked_count": report.blocked,
                "candidates": report.candidates,
                "queries_generated": report.queries_generated,
                "raw_results": report.raw_results,
                "after_dedup": report.after_dedup,
                "query": {"topic": topic, "keywords": keywords, "provider": "topic-search"},
            })

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


# ── In-memory task state store ──
import threading
_task_states = {}
_task_lock = threading.Lock()


def _task_state(run_id, **kw):
    with _task_lock:
        _task_states[run_id] = {**_task_states.get(run_id, {}), **kw}
        return _task_states[run_id]


# ── Run Shadow Task ──
@app.route("/api/tasks/run-shadow", methods=["POST"])
def run_shadow_task():
    blocked, reason = _security_check()
    if blocked:
        return jsonify({"error": reason}), 403

    data = request.get_json(silent=True) or {}
    task_id = data.get("task_id", f"shadow_task_{int(time.time())}")
    url_file = data.get("url_file", "acs_data/discovery/selected_urls.txt")
    max_urls = int(data.get("max_urls", 20))
    rate_limit = float(data.get("rate_limit", 0.3))

    # Path safety: only allow files within project acs_data/ or discovery/
    import os as _os
    abs_path = _os.path.abspath(url_file)
    allowed_prefixes = [
        _os.path.abspath("acs_data"),
        _os.path.abspath("urls"),
    ]
    if not any(abs_path.startswith(p) for p in allowed_prefixes):
        if not abs_path.replace("\\", "/").startswith(
            _os.path.abspath(".").replace("\\", "/") + "/acs_data"
        ):
            return jsonify({"error": "url_file path not allowed"}), 403

    run_id = f"shadow_run_{int(time.time()*1000)}"
    mode = "shadow"

    _task_state(run_id,
        task_id=task_id, status="running", total=0, success=0, failed=0,
        progress=0.0, message="正在启动采集...", mode=mode, url_file=url_file,
    )

    # Run in background thread
    def _do_run():
        _task_state(run_id, message="正在采集...")
        try:
            cmd = [
                sys.executable, "-m", "acs.scripts.run_shadow_batch",
                "--urls", url_file,
                "--site-id", task_id,
                "--max-urls", str(max_urls),
                "--rate-limit", str(rate_limit),
            ]
            env = {**_os.environ, "ACS_MODE": "shadow"}
            p = subprocess.run(cmd, capture_output=True, text=True,
                               timeout=300, cwd=_os.getcwd(), env=env,
                               shell=False)

            # Parse output for summary
            out = p.stdout + p.stderr
            total = max_urls
            ok = out.count(" status=ok") or out.count("status: ok") or out.count("✓")
            failed_count = max(0, total - ok) if ok < total else 0

            _task_state(run_id,
                status="completed" if p.returncode == 0 else "completed_with_errors",
                total=total, success=ok, failed=failed_count,
                progress=1.0, message=f"采集完成: {ok} 成功, {failed_count} 失败",
            )
        except subprocess.TimeoutExpired:
            _task_state(run_id, status="failed", message="采集超时")
        except Exception as e:
            _task_state(run_id, status="failed", message=f"采集异常: {str(e)}")

    t = threading.Thread(target=_do_run, daemon=True)
    t.start()

    return jsonify({
        "run_id": run_id,
        "task_id": task_id,
        "status": "running",
        "mode": mode,
    })


# ── Task Status ──
@app.route("/api/tasks/status")
def task_status():
    run_id = request.args.get("run_id", "")
    if not run_id:
        return jsonify({"error": "run_id required"}), 400
    with _task_lock:
        state = _task_states.get(run_id)
    if not state:
        return jsonify({"status": "not_found", "message": "任务未找到"})
    return jsonify(state)


# ── Results List ──
@app.route("/api/results/list")
def results_list():
    run_id = request.args.get("run_id", "")
    limit = int(request.args.get("limit", 100))

    shadow_log = "acs_shadow_logs/acs_shadow.jsonl"
    rows = []
    if os.path.exists(shadow_log):
        with open(shadow_log, encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i >= limit:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    rows.append({
                        "index": i + 1,
                        "url": entry.get("url", ""),
                        "title": entry.get("title", ""),
                        "description": entry.get("description", entry.get("body", ""))[:200],
                        "price": entry.get("price", ""),
                        "status": "success" if entry.get("ok") else "failed",
                        "failure_reason": entry.get("error", entry.get("reason", "")),
                        "collected_at": entry.get("timestamp", ""),
                    })
                except json.JSONDecodeError:
                    continue

    return jsonify({"run_id": run_id or "latest", "rows": rows, "total": len(rows)})


# ── Results Export ──
@app.route("/api/results/export", methods=["POST"])
def results_export():
    blocked, reason = _security_check()
    if blocked:
        return jsonify({"error": reason}), 403

    data = request.get_json(silent=True) or {}
    fmt = data.get("format", "json").lower()
    if fmt not in ("json", "csv", "markdown"):
        return jsonify({"error": f"unsupported format: {fmt}"}), 400

    # Load results from shadow log
    shadow_log = "acs_shadow_logs/acs_shadow.jsonl"
    rows = []
    if os.path.exists(shadow_log):
        with open(shadow_log, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    rows.append({
                        "url": entry.get("url", ""),
                        "title": entry.get("title", ""),
                        "description": entry.get("description", entry.get("body", ""))[:300],
                        "price": entry.get("price", ""),
                        "status": "success" if entry.get("ok") else "failed",
                        "failure_reason": entry.get("error", entry.get("reason", "")),
                        "collected_at": entry.get("timestamp", ""),
                    })
                except json.JSONDecodeError:
                    continue

    ts = time.strftime("%Y%m%d-%H%M%S")
    out_dir = "acs_data/exports"
    os.makedirs(out_dir, exist_ok=True)

    if fmt == "json":
        out_path = os.path.join(out_dir, f"export_{ts}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)
    elif fmt == "csv":
        out_path = os.path.join(out_dir, f"export_{ts}.csv")
        import csv as _csv
        with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
            if rows:
                w = _csv.DictWriter(f, fieldnames=rows[0].keys())
                w.writeheader()
                w.writerows(rows)
    elif fmt == "markdown":
        out_path = os.path.join(out_dir, f"export_{ts}.md")
        with open(out_path, "w", encoding="utf-8") as f:
            if rows:
                f.write("| # | URL | 标题 | 状态 |\n")
                f.write("|---|-----|------|------|\n")
                for i, r in enumerate(rows, 1):
                    st = "[PASS]" if r["status"] == "success" else "[FAIL]"
                    f.write(f"| {i} | {r['url'][:60]} | {r['title'][:40]} | {st} |\n")

    return jsonify({
        "format": fmt,
        "path": out_path,
        "total": len(rows),
        "message": f"Exported {len(rows)} rows to {out_path}",
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
