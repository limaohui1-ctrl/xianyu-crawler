"""ACS Web Dashboard — Flask, 127.0.0.1 only."""
import os, sys, json, time
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJ = os.path.dirname(os.path.dirname(_HERE))
if _PROJ not in sys.path: sys.path.insert(0, _PROJ)
from flask import Flask, render_template_string, jsonify, request
from acs.web.auth import require_auth

app = Flask(__name__, template_folder="templates")
app.secret_key = os.urandom(24).hex()

CSS = "body{font-family:system-ui,sans-serif;background:#0d1117;color:#c9d1d9;margin:0}nav{background:#161b22;padding:12px 20px;border-bottom:1px solid #30363d}nav a{color:#58a6ff;text-decoration:none;margin-right:16px;font-size:14px}main{padding:20px;max-width:1200px;margin:auto}table{border-collapse:collapse;width:100%;margin:12px 0}th,td{border:1px solid #30363d;padding:8px 12px;text-align:left;font-size:13px}th{background:#161b22}.card{background:#161b22;border:1px solid #30363d;border-radius:6px;padding:16px;margin:12px 0}.metric{font-size:24px;font-weight:bold;color:#58a6ff}.ok{color:#3fb950}.warn{color:#d29922}.err{color:#f85149}.btn{background:#238636;color:#fff;border:none;padding:6px 14px;border-radius:4px;cursor:pointer;font-size:13px}.btn:hover{background:#2ea043}.btn-danger{background:#da3633}.btn-danger:hover{background:#f85149}input,select{background:#0d1117;color:#c9d1d9;border:1px solid #30363d;padding:6px 10px;border-radius:4px;font-size:13px}.footer{text-align:center;color:#8b949e;font-size:12px;padding:20px;border-top:1px solid #30363d;margin-top:20px}"

NAV = '<nav><a href="/">Overview</a><a href="/shadow">Shadow</a><a href="/cost">Cost</a><a href="/reviews">Reviews</a><a href="/charts">Charts</a><a href="/structure">Structure</a><a href="/audit">Audit</a><a href="/evaluation">Evaluation</a><a href="/reports">Reports</a></nav>'

FOOTER = '<div class="footer">ACS Dashboard v1.0 | ACS_MODE=shadow | No auto-apply | 127.0.0.1</div>'

BASE_HTML = f"<!DOCTYPE html><html lang=zh><head><meta charset=utf-8><title>ACS Dashboard</title><style>{CSS}</style></head><body>{NAV}<main>{{content}}</main>{FOOTER}</body></html>"

def render_body(body):
    return render_template_string(BASE_HTML.replace("{content}", body))

# ── Routes ──
@app.route("/")
def index(): return render_body(overview_content())

@app.route("/shadow")
def shadow(): return render_body(shadow_content())

@app.route("/cost")
def cost_page(): return render_body(cost_content())

@app.route("/reviews")
def reviews(): return render_body(reviews_content())

@app.route("/structure")
def structure(): return render_body(structure_content())

@app.route("/audit")
def audit(): return render_body(audit_content())

@app.route("/reports")
def evaluation(): return render_body(evaluation_content())
@app.route("/reports")
def reports(): return render_body(reports_content())

# ── API ──
@app.route("/api/overview")
def api_overview(): return jsonify(get_overview_data())

ACTION_MGR = None
def get_am():
    global ACTION_MGR
    if ACTION_MGR is None:
        from acs.web.safe_actions import SafeActionManager
        ACTION_MGR = SafeActionManager()
    return ACTION_MGR

def _review_action(action):
    data = request.get_json() or {}
    rid = data.get("review_id", 0)
    note = data.get("note", "")
    am = get_am()
    if action == "approve": return jsonify(am.approve(rid, note))
    if action == "reject": return jsonify(am.reject(rid, note))
    if action == "needs_more_data": return jsonify(am.needs_more_data(rid, note))
    if action == "archive": return jsonify(am.archive(rid))
    return jsonify({"error": "unknown action"}), 400

@app.route("/api/reviews/approve", methods=["POST"])
@require_auth
def api_approve(): return _review_action("approve")

@app.route("/api/reviews/reject", methods=["POST"])
@require_auth
def api_reject(): return _review_action("reject")

@app.route("/api/reviews/needs_more_data", methods=["POST"])
@require_auth
def api_needs_more(): return _review_action("needs_more_data")

@app.route("/api/reviews/archive", methods=["POST"])
@require_auth
def api_archive(): return _review_action("archive")

# ── Chart data API routes (readonly) ──
@app.route("/api/charts/shadow_trend")
def api_shadow_trend():
    from acs.web.charts import shadow_trend_data
    return shadow_trend_data()

@app.route("/api/charts/ai_call_trend")
def api_ai_call_trend():
    from acs.web.charts import ai_call_trend_data
    return ai_call_trend_data()

@app.route("/api/charts/parser_distribution")
def api_parser_distribution():
    from acs.web.charts import parser_distribution_data
    return parser_distribution_data()

@app.route("/api/charts/review_status")
def api_review_status():
    from acs.web.charts import review_status_data
    return review_status_data()

@app.route("/api/charts/structure_trend")
def api_structure_trend():
    from acs.web.charts import structure_trend_data
    return structure_trend_data()

@app.route("/charts")
def charts_page():
    return render_body(charts_content())

@app.route("/api/export/<fmt>")
def api_export(fmt):
    from acs.dashboard.cli_dashboard import CLIDashboard
    dash = CLIDashboard(review_store=get_review_store(), structure_store=get_struct_store())
    result = dash.export(fmt=fmt)
    if fmt == "json": return jsonify(json.loads(result))
    return f"<pre>{result}</pre>"

# ── Harvest API ──
@app.route("/api/harvest/run", methods=["POST"])
@require_auth
def api_harvest_run():
    """Run content harvest on selected URLs or custom URL list."""
    data = request.get_json() or {}
    urls = data.get("urls", [])
    keywords = data.get("keywords", [])
    include_duplicates = data.get("include_duplicates", True)

    if not urls:
        # Try loading from selected_urls.txt
        try:
            with open("acs_data/discovery/selected_urls.txt", encoding="utf-8") as f:
                urls = [line.strip() for line in f if line.strip()]
        except Exception:
            pass

    if not urls:
        return jsonify({"error": "No URLs provided", "results": [], "stats": {}}), 400

    from acs.content.content_harvest_pipeline import run_harvest
    results = run_harvest(urls, keywords=keywords, include_duplicates=include_duplicates)

    stats = results[0].pop("_harvest_stats", {}) if results else {}
    return jsonify({"results": results, "stats": stats})


@app.route("/api/harvest/export/<fmt>")
def api_harvest_export(fmt):
    """Export harvest results in specified format."""
    # Load most recent harvest results
    import glob as _g
    json_files = sorted(_g.glob("acs_data/harvest/harvest_*.json"), reverse=True)
    if not json_files:
        return jsonify({"error": "No harvest results found"}), 404

    with open(json_files[0], encoding="utf-8") as f:
        results = json.load(f)

    if fmt == "json":
        return jsonify({"results": results})

    if fmt == "csv":
        from acs.content.content_harvest_pipeline import harvest_to_csv_string
        csv_content = harvest_to_csv_string(results)
        return csv_content, 200, {"Content-Type": "text/csv; charset=utf-8",
                                   "Content-Disposition": "attachment; filename=harvest.csv"}

    if fmt == "excel" or fmt == "xlsx":
        from acs.content.export_excel import export_excel, is_excel_available
        if not is_excel_available():
            return jsonify({"error": "openpyxl not installed"}), 500
        try:
            path = export_excel(results)
            return jsonify({"file": path, "format": "xlsx"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    if fmt == "markdown":
        from acs.content.content_harvest_pipeline import harvest_to_markdown_string
        md_content = harvest_to_markdown_string(results)
        return f"<pre>{md_content}</pre>"

    return jsonify({"error": f"Unknown format: {fmt}"}), 400


@app.route("/api/harvest/export-file/<fmt>")
def api_harvest_export_file(fmt):
    """Export harvest results to file, return path."""
    import glob as _g
    json_files = sorted(_g.glob("acs_data/harvest/harvest_*.json"), reverse=True)
    if not json_files:
        return jsonify({"error": "No harvest results found"}), 404

    with open(json_files[0], encoding="utf-8") as f:
        results = json.load(f)

    if fmt == "csv":
        from acs.content.content_harvest_pipeline import _save_csv
        import time as _t
        path = f"acs_data/harvest/harvest_{_t.strftime('%Y%m%d_%H%M%S')}.csv"
        _save_csv(results, path)
        return jsonify({"file": os.path.abspath(path), "format": "csv"})

    if fmt == "xlsx" or fmt == "excel":
        from acs.content.export_excel import export_excel, is_excel_available
        if not is_excel_available():
            return jsonify({"error": "openpyxl not installed"}), 500
        try:
            path = export_excel(results)
            return jsonify({"file": os.path.abspath(path), "format": "xlsx"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    if fmt == "markdown":
        from acs.content.content_harvest_pipeline import _save_markdown
        import time as _t
        path = f"acs_data/harvest/harvest_{_t.strftime('%Y%m%d_%H%M%S')}.md"
        _save_markdown(results, path)
        return jsonify({"file": os.path.abspath(path), "format": "md"})

    return jsonify({"error": f"Unknown format: {fmt}"}), 400


@app.route("/api/harvest/status")
def api_harvest_status():
    """Get harvest status: latest results summary, available exports."""
    import glob as _g
    json_files = sorted(_g.glob("acs_data/harvest/harvest_*.json"), reverse=True)
    if not json_files:
        return jsonify({"status": "no_data", "count": 0})

    with open(json_files[0], encoding="utf-8") as f:
        results = json.load(f)

    stats = {}
    if results and "_harvest_stats" in results[0]:
        stats = results[0]["_harvest_stats"]

    return jsonify({
        "status": "ready",
        "count": len(results),
        "latest_file": json_files[0],
        "stats": stats,
    })

# ── Content helpers ──
def overview_content():
    d = get_overview_data()
    s = d.get("shadow", {}); c = d.get("cost", {}); r = d.get("reviews", {})
    al = d.get("alerts", [])
    ah = ""
    for a in al:
        cls = "err" if a.get("severity") == "high" else "warn"
        ah += f'<div class="card"><span class="{cls}">[{a.get("severity","info").upper()}]</span> {a.get("message","")}</div>'
    return f"""<h1>ACS Dashboard Overview</h1>{ah}
<div class="card"><div class="metric">{s.get("total_shadow",0)}</div>Shadow entries<br><small>Success: {s.get("success_rate",0):.1%}</small></div>
<div class="card"><div class="metric">{c.get("total_calls",0)}</div>AI calls<br><small>Cost: ${c.get("total_cost",0):.6f}</small></div>
<div class="card"><div class="metric">{r.get("pending",0)}</div>Pending reviews<br><small>Done: {r.get("approved",0)}</small></div>
<div class="card"><div class="metric">{d.get("errors",0)}</div>Errors</div>
<div class="card"><b>Safety:</b> ACS_MODE={d.get("acs_mode","shadow")} | Auto-apply={d.get("auto_apply",False)}</div>"""

def shadow_content():
    from acs.dashboard.shadow_view import ShadowView
    v = ShadowView(shadow_stats=get_shadow_data())
    return v.markdown().replace("\n","<br>")

def cost_content():
    from acs.dashboard.cost_view import CostView
    return CostView().markdown().replace("\n","<br>")

def reviews_content():
    from acs.dashboard.review_queue_view import ReviewQueueView
    store = get_review_store()
    if not store: return "<h1>Reviews</h1><p>No review store configured.</p>"
    v = ReviewQueueView(store)
    pending = v.get_pending(limit=50)
    rows = ""
    for p in pending:
        rid = p.get("id","")
        rows += f'<tr><td>{rid}</td><td>{p.get("field_name","")}</td><td>{p.get("old_selector","")}</td><td>{p.get("candidate_selector","")}</td><td>{p.get("confidence",0):.2f}</td><td><button class="btn" onclick="act({rid},&apos;approve&apos;)">Approve</button> <button class="btn btn-danger" onclick="act({rid},&apos;reject&apos;)">Reject</button></td></tr>'
    return f"""<h1>Review Queue</h1><table><tr><th>ID</th><th>Field</th><th>Old</th><th>New</th><th>Conf</th><th>Action</th></tr>{rows}</table>
<script>function act(id,action){{var note=prompt('Note:');fetch('/api/reviews/'+action,{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{review_id:id,note:note||''}})}}).then(r=>r.json()).then(d=>{{alert(JSON.stringify(d));location.reload()}})}}</script>"""

def structure_content():
    store = get_struct_store()
    if not store: return "<h1>Structure</h1><p>No store.</p>"
    from acs.dashboard.structure_view import StructureView
    return StructureView(store).markdown().replace("\n","<br>")

def audit_content():
    from acs.observability.ai_call_audit import AICallAuditor
    au = AICallAuditor("logs/ai_call_audit.jsonl")
    entries = au.read_logs(limit=50)
    rows = ""
    for e in entries:
        cls = "ok" if e.get("success") else "err"
        tok = e.get("tokens_prompt",0)+e.get("tokens_completion",0)
        rows += f'<tr><td>{e.get("timestamp","")}</td><td>{e.get("url","")[:50]}</td><td>{tok}</td><td class="{cls}">{e.get("success")}</td><td>{e.get("error","")[:60]}</td></tr>'
    return f"<h1>AI Call Audit</h1><table><tr><th>Time</th><th>URL</th><th>Tokens</th><th>Status</th><th>Error</th></tr>{rows}</table>"

def charts_content():
    ch_data = json.dumps(get_chart_data())
    return f"""<h1>Charts</h1>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:20px">
<div class="card"><canvas id="c1"></canvas></div>
<div class="card"><canvas id="c2"></canvas></div>
<div class="card"><canvas id="c3"></canvas></div>
<div class="card"><canvas id="c4"></canvas></div>
<div class="card"><canvas id="c5"></canvas></div>
<div class="card"><canvas id="c6"></canvas></div>
</div>
<script>
var d=JSON.parse('{ch_data}');
function mk(id,tp,lb,dat,ylab){{
  if(!lb||lb.length===0){{document.getElementById(id).parentElement.innerHTML='<p style=text-align:center;color:#8b949e>No data</p>';return;}}
  new Chart(document.getElementById(id),{{type:tp,data:{{labels:lb,datasets:dat}},options:{{responsive:true,plugins:{{legend:{{position:'bottom',labels:{{color:'#c9d1d9'}}}}}},scales:{{y:{{title:{{display:true,text:ylab||'',color:'#8b949e'}},ticks:{{color:'#8b949e'}}}},x:{{ticks:{{color:'#8b949e',maxRotation:45}}}}}}}}}});
}}
mk('c1','line',d.shadow_labels,[{{label:'Success',data:d.shadow_success,borderColor:'#3fb950',tension:0.2}}],'Rate');
mk('c2','line',d.ai_labels,[{{label:'Tokens',data:d.ai_tokens,borderColor:'#58a6ff',tension:0.2,yAxisID:'y'}},{{label:'Cost ($)',data:d.ai_cost,borderColor:'#d29922',tension:0.2,yAxisID:'y1'}}],'Tokens');
mk('c3','bar',d.parser_labels,[{{label:'Count',data:d.parser_values,backgroundColor:'#58a6ff'}}],'URLs');
mk('c4','doughnut',d.review_labels,[{{label:'Reviews',data:d.review_values,backgroundColor:['#238636','#da3633','#d29922','#8b949e','#58a6ff']}}],'');
mk('c5','line',d.struct_labels,[{{label:'Change Score',data:d.struct_scores,borderColor:'#f85149',tension:0.2}}],'Score');
mk('c6','bar',d.site_labels,[{{label:'Success Rate',data:d.site_rates,backgroundColor:'#3fb950'}}],'Rate');
</script>"""

def get_chart_data():
    shadow = {"labels":[],"success":[]}; ai = {"labels":[],"tokens":[],"cost":[]}
    parser = {"labels":[],"values":[]}; review = {"labels":[],"values":[]}
    struct = {"labels":[],"scores":[]}; site = {"labels":[],"rates":[]}
    try:
        import json as _j; import os as _os
        if _os.path.exists("acs_shadow_logs/acs_shadow.jsonl"):
            with open("acs_shadow_logs/acs_shadow.jsonl",encoding="utf-8") as f:
                entries=[_j.loads(l) for l in f if l.strip()]
            shadow["labels"]=[e.get("ts","")[5:16] for e in entries[-30:]]
            shadow["success"]=[1 if e.get("acs_success") else 0 for e in entries[-30:]]
            dist={}
            for e in entries:
                p=e.get("acs_parser","unknown"); dist[p]=dist.get(p,0)+1
                u=e.get("url",""); d2=u.split("/")[2] if "/" in u else u[:30]
                site.setdefault(d2,{"total":0,"ok":0})
                site[d2]["total"]+=1
                if e.get("acs_success"): site[d2]["ok"]+=1
            parser["labels"]=list(dist.keys()); parser["values"]=list(dist.values())
            for k,v in site.items():
                site["labels"].append(k); site["rates"].append(v["ok"]/max(v["total"],1))
        if _os.path.exists("logs/ai_call_audit.jsonl"):
            with open("logs/ai_call_audit.jsonl",encoding="utf-8") as f:
                ae=[_j.loads(l) for l in f if l.strip()]
            ai["labels"]=[e.get("timestamp","")[5:16] for e in ae[-30:]]
            ai["tokens"]=[e.get("tokens_prompt",0)+e.get("tokens_completion",0) for e in ae[-30:]]
            ai["cost"]=[e.get("estimated_cost",0) for e in ae[-30:]]
        try:
            from acs.storage.repair_review_store import RepairReviewStore
            rs=RepairReviewStore("acs_data/reviews.db")
            by=rs.get_stats().get("by_status",{})
            review["labels"]=list(by.keys()); review["values"]=list(by.values())
        except Exception:  # module may not be loaded
            pass
        try:
            from acs.storage.structure_history_store import StructureHistoryStore
            ss=StructureHistoryStore("acs_data/structure_history.db")
            rows=ss.get_recent("",limit=30)
            struct["labels"]=[r.get("captured_at","")[5:16] for r in rows]
            struct["scores"]=[r.get("change_score",0) for r in rows]
        except Exception:  # module may not be loaded
            pass
    except Exception:  # chart data loading best-effort
        pass
    return {
        "shadow_labels":shadow["labels"],"shadow_success":shadow["success"],
        "ai_labels":ai["labels"],"ai_tokens":ai["tokens"],"ai_cost":ai["cost"],
        "parser_labels":parser["labels"],"parser_values":parser["values"],
        "review_labels":review["labels"],"review_values":review["values"],
        "struct_labels":struct["labels"],"struct_scores":struct["scores"],
        "site_labels":site.get("labels",[]),"site_rates":site.get("rates",[]),
    }

def evaluation_content():
    from acs.evaluation.on_mode_readiness import evaluate_from_shadow, summary
    from acs.evaluation.risk_classifier import RiskClassifier
    rs, extra = evaluate_from_shadow()
    sm = summary(rs, extra)
    rc = RiskClassifier()
    rc.classify(rs, "default")
    blocks = rc.blocking_reasons()
    br = "".join(f"<li>{b}</li>" for b in blocks) if blocks else "<li>None</li>"
    cp = "<p>Canary plan generated. See <code>acs/evaluation/canary_plan.py</code>.</p>"
    rp = "<p>Rollback plan generated. See <code>acs/evaluation/rollback_plan.py</code>.</p>"
    ap_gate = "<p>No active canary approvals.</p>"
    canary_status = "<p>No active canary runs. Run <code>python -m acs.ops.canary_runner --dry-run</code> to test.</p>"
    try:
        from acs.evaluation.manual_approval_gate import ApprovalGate
        gate = ApprovalGate()
        latest = gate.get_latest("public_test_ecommerce")
        if latest and latest.is_valid():
            ap_gate = f"<p class=ok>Approved by {latest.reviewer} on {latest.reviewed_at}</p>"
        elif latest:
            ap_gate = f"<p class=warn>Latest: {latest.decision} by {latest.reviewer}</p>"
    except Exception:  # approval gate may not be configured
        pass
    try:
        from acs.ops.canary_runner import CanaryRunner
        cr = CanaryRunner()
        r = cr.dry_run("public_test_ecommerce")
        if r.get("status") == "dry_run_complete":
            canary_status = f"<p class=ok>Canary dry-run: {r.get('status','')}. Steps: {len(r.get('steps',[]))}</p>"
        else:
            canary_status = f"<p class=warn>Canary blocked: {r.get('reason','?')}</p>"
    except Exception as e:
        canary_status = f"<p class=warn>Canary check: {str(e)[:80]}</p>"
    return f"""<h1>On-Mode Readiness Evaluation</h1>
<div class="card"><h2>Summary</h2>
<table><tr><td>Samples</td><td>{rs.sample_count}</td></tr>
<tr><td>Success Rate</td><td>{rs.success_rate:.1%}</td></tr>
<tr><td>Avg Completeness</td><td>{rs.avg_completeness:.1%}</td></tr>
<tr><td>Severe Error Rate</td><td>{rs.severe_error_rate:.1%}</td></tr>
<tr><td>Readiness Score</td><td class="metric">{rs.score:.4f}</td></tr>
<tr><td>Level</td><td class="{chr(34)}{'ok' if rs.level=='READY' else 'warn' if rs.level=='NOT_READY' else 'err'}{chr(34)}"><b>{rs.level}</b></td></tr>
<tr><td>Recommendation</td><td><b>{sm.get('recommendation','')}</b></td></tr></table></div>
<div class="card"><h2>Blocking Reasons</h2><ul>{br}</ul></div>
<div class="card"><h2>Canary Plan</h2>{cp}</div>
<div class="card"><h2>Rollback Plan</h2>{rp}</div>
<div class="card"><h2>Canary Status</h2>{canary_status}</div>
<div class="card"><h2>Manual Approval Status</h2>{ap_gate}</div>
<div class="card"><p><b>Safety:</b> ACS_MODE=shadow. No auto-switch. Manual approval required for canary.</p></div>"""

def reports_content():
    return """<h1>Reports</h1>
<div class="card"><h3>Export</h3><a href="/api/export/markdown" class="btn">Markdown</a> <a href="/api/export/json" class="btn">JSON</a></div>
<div class="card"><h3>Daily Report</h3><code>python -m acs.ops.daily_report</code></div>
<div class="card"><h3>Weekly Report</h3><code>python -m acs.ops.weekly_report</code></div>"""

# ── Data singletons ──
_RVS = None
def get_review_store():
    global _RVS
    if _RVS is None:
        try:
            from acs.storage.repair_review_store import RepairReviewStore
            _RVS = RepairReviewStore("acs_data/reviews.db")
        except Exception:  # module may not be loaded
            pass
    return _RVS

_SS = None
def get_struct_store():
    global _SS
    if _SS is None:
        try:
            from acs.storage.structure_history_store import StructureHistoryStore
            _SS = StructureHistoryStore("acs_data/structure_history.db")
        except Exception:  # module may not be loaded
            pass
    return _SS

def get_shadow_data():
    try:
        from acs.observability.shadow_analyzer import ShadowAnalyzer
        sa = ShadowAnalyzer("acs_shadow_logs/acs_shadow.jsonl")
        return sa.analyze().to_dict()
    except: return {}

def get_overview_data():
    shadow = get_shadow_data()
    cost = {}
    try:
        from acs.observability.ai_call_audit import AICallAuditor
        cost = AICallAuditor("logs/ai_call_audit.jsonl").get_stats()
    except Exception:  # audit log may not exist
        pass
    reviews = {"pending":0, "approved":0}
    try:
        store = get_review_store()
        if store:
            s = store.get_stats()
            by = s.get("by_status", {})
            reviews = {"pending": by.get("pending_review",0), "approved": by.get("approved",0)}
    except Exception:  # review store may not exist
        pass
    from acs.ops.alert_rules import AlertEngine
    engine = AlertEngine()
    alerts = engine.check({
        "ai_fail_rate": cost.get("failed_calls",0)/max(cost.get("total_calls",1),1),
        "cost_ratio": cost.get("estimated_cost",0)/0.5,
        "shadow_success_rate": shadow.get("acs_success_rate",1),
        "pending_reviews": reviews.get("pending",0),
    })
    return {
        "shadow": {"total_shadow": shadow.get("total_entries",0), "success_rate": shadow.get("acs_success_rate",0)},
        "cost": {"total_calls": cost.get("total_calls",0), "total_cost": cost.get("estimated_cost",0)},
        "reviews": reviews,
        "alerts": [a.to_dict() for a in alerts],
        "errors": cost.get("failed_calls",0),
        "acs_mode": "shadow",
        "auto_apply": False,
    }

def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8050)
    p.add_argument("--debug", action="store_true")
    args = p.parse_args()
    print(f"ACS Dashboard: http://{args.host}:{args.port}")
    print("ACS_MODE=shadow | No auto-apply | 127.0.0.1 only")
    app.run(host=args.host, port=args.port, debug=args.debug)

if __name__ == "__main__":
    main()
