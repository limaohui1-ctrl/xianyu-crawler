"""On-mode readiness — evaluates shadow data against admission gates.

Returns READY / NOT_READY / BLOCKED / INSUFFICIENT_DATA.
NEVER auto-switches ACS_MODE.

v2: Properly classifies pages, excludes auth/error entries from success metrics.
"""
import os, json, sys, time
from urllib.parse import urlparse
from acs.evaluation.readiness_score import compute_readiness_score, ReadinessScore

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJ = os.path.dirname(os.path.dirname(_HERE))
if _PROJ not in sys.path: sys.path.insert(0, _PROJ)

DEFAULT_SHADOW_LOG = "acs_shadow_logs/acs_shadow.jsonl"
DEFAULT_AUDIT_LOG = "logs/ai_call_audit.jsonl"

# ── Page type classifier ──
def classify_page(url: str, html_preview: str = "", entry: dict = None) -> str:
    """Classify a URL/entry into a page type."""
    u = url.lower()
    # Error indicators
    if entry:
        acs_error = str(entry.get("acs_error", "")).lower()
        for indicator in ["401", "403", "unauthorized", "forbidden", "auth required",
                          "not authorized", "access denied", "login", "captcha"]:
            if indicator in acs_error:
                return "auth_required"
        body = str(entry.get("legacy_body", "")).lower()
        if body and ("unauthorized" in body[:500] or "access denied" in body[:500]):
            return "auth_required"
    # JSON API endpoints (also catch known JSON-only sites)
    api_indicators = ["/api/", "/v1/", "/v2/", "/v3/", "/v4/", ".json",
                      "api.", "graphql", "/rest/", "/graphql"]
    json_only_sites = ["dummyjson.com"]
    if any(x in u for x in api_indicators) or any(s in u for s in json_only_sites):
        if "jsonplaceholder" not in u:
            return "json_api"
    # CSV/XML
    if u.endswith(".csv"): return "csv_dataset"
    if u.endswith((".xml", ".rss", ".atom")): return "xml_feed"
    if u.endswith((".txt", ".md", ".robots.txt", ".geojson")): return "text_document"
    # ── Product detail page (single item, has explicit product ID) ──
    detail_indicators = [
        "/index.html",                            # toscrape detail
        "/ajax/product/", "/static/product/",     # webscraper product pages
        "/allinone/product/",                     # webscraper allinone product
        "/dp/", "/gp/product/",                  # Amazon
        "/itm/",                                  # eBay
        "/ip/",                                   # Walmart
        "/site/",                                 # BestBuy
        "/listing/",                               # Etsy / general
        "/product/",                               # DHgate / general
        "/item/",                                  # AliExpress / Rakuten / general
        "/products/",                              # Lazada / Shopee
        "/us/en/p/",                               # IKEA (only matches IKEA pattern)
        "/hotel/", "/rooms/",                      # Booking / Airbnb
        "gsmarena.com/",                           # GSMArena phone specs
    ]
    is_detail = any(x in u for x in detail_indicators)
    # ── Product category/list page ──
    list_indicators = [
        "/catalogue/page-", "/catalogue/category/",
        "/computers", "/phones", "/tablets",
        "/allinone", "/static", "/more", "/ajax/",
        "/test-sites/e-commerce", "/search?", "/browse/",
    ]
    is_list = any(x in u for x in list_indicators)
    # Distinguish: detail takes priority over list
    if is_detail:
        return "html_product_detail_page"
    if is_list:
        return "html_product_list_page"
    # Generic product indicators (fallback)
    product_indicators = [
        "/product/", "/item/", "/shop/", "/goods/", "/detail/",
        "/listing/", "/p/", "/dp/", "/products/",
    ]
    if any(x in u for x in product_indicators):
        return "html_product_page"
    # HTML generic pages
    html_indicators = [".html", ".htm", "/search", "/posts/", "/articles/",
                       "/blog/", "/page/", "www.w3.org", "example.com"]
    if any(x in u for x in html_indicators) or not any(x in u for x in api_indicators):
        return "html_generic_page"
    return "unknown"


def load_shadow_entries(shadow_log_path: str = None) -> list:
    path = shadow_log_path or DEFAULT_SHADOW_LOG
    if not os.path.exists(path): return []
    entries = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try: entries.append(json.loads(line))
            except Exception:  # skip malformed JSON lines
                pass
    return entries


def classify_all_entries(entries: list) -> dict:
    """Classify entries into page types and return breakdown."""
    cats = {
        "json_api": [], "csv_dataset": [], "xml_feed": [], "text_document": [],
        "html_generic_page": [], "auth_required": [], "unknown": [],
    }
    for e in entries:
        pt = classify_page(e.get("url", ""), entry=e)
        cats.setdefault(pt, []).append(e)
    return cats


def evaluate_from_shadow(shadow_log_path: str = None, audit_log_path: str = None) -> ReadinessScore:
    entries = load_shadow_entries(shadow_log_path)
    all_count = len(entries)
    if all_count == 0:
        return compute_readiness_score(sample_count=0), {"all_count": 0, "valid_count": 0, "excluded_count": 0, "type_stats": {}, "page_types": {}}

    cats = classify_all_entries(entries)

    # ── Exclude auth_required from valid samples ──
    excluded = cats.get("auth_required", [])
    valid = [e for e in entries if e not in excluded]
    valid_count = len(valid)

    if valid_count == 0:
        return compute_readiness_score(sample_count=all_count), {"all_count": all_count, "valid_count": 0, "excluded_count": len(excluded), "type_stats": {}, "page_types": {}}

    successes = sum(1 for e in valid if e.get("acs_success"))
    completeness_vals = [e.get("acs_completeness", 0) for e in valid if e.get("acs_success")]
    severe_errors = sum(1 for e in valid
                        if e.get("acs_error") and ("401" in str(e.get("acs_error","")) or
                           "500" in str(e.get("acs_error","")) or
                           "timeout" in str(e.get("acs_error","")).lower()))

    # AI cost
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
                except Exception:  # skip malformed audit log entries
                    pass
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
    except Exception:  # review store may not exist
        pass

    # Per-type stats
    type_stats = {}
    for pt, items in cats.items():
        if not items: continue
        t_success = sum(1 for e in items if e.get("acs_success"))
        t_comp_vals = [e.get("acs_completeness", 0) for e in items if e.get("acs_success")]
        type_stats[pt] = {
            "count": len(items),
            "success_count": t_success,
            "success_rate": t_success / max(len(items), 1),
            "avg_completeness": sum(t_comp_vals) / max(len(t_comp_vals), 1),
        }

    return compute_readiness_score(
        sample_count=valid_count,
        success_rate=successes / max(valid_count, 1),
        avg_completeness=sum(completeness_vals) / max(len(completeness_vals), 1) / 100.0,
        severe_error_rate=severe_errors / max(valid_count, 1),
        cost_ratio=cost_ratio,
        api_key_leak_count=0,
        old_flow_impact_count=0,
        high_risk_pending=high_risk,
    ), {"all_count": all_count, "valid_count": valid_count, "excluded_count": len(excluded),
        "type_stats": type_stats, "page_types": {pt: len(items) for pt, items in cats.items()}}


def summary(rs: ReadinessScore, extra: dict = None) -> dict:
    d = rs.to_dict()
    d["recommendation"] = "KEEP_SHADOW"
    if rs.level == "READY" and rs.score >= 0.85:
        d["recommendation"] = "READY_FOR_CANARY"
    elif rs.level == "BLOCKED":
        d["recommendation"] = "BLOCKED_FIX_REQUIRED"
    elif rs.level == "INSUFFICIENT_DATA":
        d["recommendation"] = "INSUFFICIENT_DATA"
    if extra:
        d.update(extra)
    return d


def evaluate_by_page_type(shadow_log_path: str = None, page_type: str = "html_product_page", audit_log_path: str = None) -> dict:
    """Evaluate readiness for only one page_type."""
    entries = load_shadow_entries(shadow_log_path)
    all_count = len(entries)
    cats = classify_all_entries(entries)
    filtered = cats.get(page_type, [])
    n = len(filtered)
    if n == 0:
        rs = compute_readiness_score(sample_count=0)
        return summary(rs, {"page_type": page_type, "filtered_count": 0, "all_count": all_count,
                            "message": f"No entries for page_type={page_type}"})

    successes = sum(1 for e in filtered if e.get("acs_success"))
    comp_vals = [e.get("acs_completeness", 0) for e in filtered if e.get("acs_success")]
    severe = sum(1 for e in filtered if e.get("acs_error") and
                 ("401" in str(e.get("acs_error","")) or "500" in str(e.get("acs_error","")) or
                  "timeout" in str(e.get("acs_error","")).lower()))

    rs = compute_readiness_score(
        sample_count=n,
        success_rate=successes / max(n, 1),
        avg_completeness=sum(comp_vals) / max(len(comp_vals), 1) / 100.0,
        severe_error_rate=severe / max(n, 1),
        cost_ratio=0.0,  # cost from audit log; omit for page-type
    )
    return summary(rs, {"page_type": page_type, "filtered_count": n, "all_count": all_count})

def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--site-id", default="default")
    p.add_argument("--page-type", default="")
    p.add_argument("--domain", default="")
    args = p.parse_args()

    if args.page_type:
        sm = evaluate_by_page_type(page_type=args.page_type)
    else:
        rs, extra = evaluate_from_shadow()
        sm = summary(rs, extra)
    sm["site_id"] = args.site_id

    # ── Domain filter ──
    if args.domain:
        entries = load_shadow_entries()
        domain_entries = [e for e in entries if args.domain in e.get("url", "")]
        dn = len(domain_entries)
        if dn:
            successes = sum(1 for e in domain_entries if e.get("acs_success"))
            comps = [e.get("acs_completeness", 0) for e in domain_entries if e.get("acs_success")]
            sm["domain"] = args.domain
            sm["domain_sample_count"] = dn
            sm["domain_success_rate"] = successes / max(dn, 1)
            sm["domain_avg_completeness"] = sum(comps) / max(len(comps), 1)
            sm["domain_info"] = f"{dn} entries, {sum(comps)/max(len(comps),1):.1f}% completeness"
        else:
            sm["domain_info"] = f"no entries for {args.domain}"
    print(json.dumps(sm, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
