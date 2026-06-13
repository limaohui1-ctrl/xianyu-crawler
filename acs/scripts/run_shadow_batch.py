#!/usr/bin/env python
"""
Shadow Batch Collector — safely accumulates ACS shadow samples in bulk.

Runs STRICTLY in ACS_MODE=shadow. Never touches legacy output.
Validates allowed_domains, rate-limits, records all failures.

Usage:
    python -m acs.scripts.run_shadow_batch --urls urls.txt --site-id mysite --max-urls 50 --rate-limit 0.5

URL file format: one URL per line, no parameters, no secrets.
"""

import argparse, json, os, sys, time, urllib.request, urllib.error

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJ = os.path.dirname(os.path.dirname(_HERE))
if _PROJ not in sys.path: sys.path.insert(0, _PROJ)


def load_urls(path: str, max_urls: int = 100) -> list:
    urls = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("http://") or line.startswith("https://"):
                urls.append(line)
                if len(urls) >= max_urls:
                    break
    return urls


def validate_domain(url: str, allowed_domains: list) -> bool:
    if not allowed_domains:
        return True
    from urllib.parse import urlparse
    domain = urlparse(url).netloc.lower()
    return any(domain == d.lower() or domain.endswith("." + d.lower()) for d in allowed_domains)


def fetch_html(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; ACS-Shadow-Batch/1.0)",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def main():
    p = argparse.ArgumentParser(description="ACS Shadow Batch Collector")
    p.add_argument("--urls", required=True, help="Text file with one URL per line")
    p.add_argument("--site-id", default="default")
    p.add_argument("--max-urls", type=int, default=100)
    p.add_argument("--rate-limit", type=float, default=1.0, help="Seconds between requests")
    p.add_argument("--timeout", type=int, default=30)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    # ── Safety: enforce ACS_MODE=shadow ──
    if os.environ.get("ACS_MODE") == "on":
        print("ERROR: ACS_MODE=on is not allowed for shadow batch. Set ACS_MODE=shadow.")
        sys.exit(1)
    os.environ["ACS_MODE"] = "shadow"

    # ── Load URLs ──
    urls = load_urls(args.urls, args.max_urls)
    print(f"Loaded {len(urls)} URLs from {args.urls}")

    # ── Validate domains from site registry ──
    allowed_domains = []
    try:
        from acs.sites.site_registry import SiteRegistry
        reg = SiteRegistry()
        site = reg.get(args.site_id)
        if site and site.allowed_domains:
            allowed_domains = site.allowed_domains
            print(f"Allowed domains: {allowed_domains}")
    except Exception:
        pass

    invalid = [u for u in urls if not validate_domain(u, allowed_domains)]
    if invalid:
        print(f"WARNING: {len(invalid)} URLs outside allowed_domains — skipped")
        urls = [u for u in urls if u not in invalid]

    if args.dry_run:
        print(f"DRY RUN — would process {len(urls)} URLs")
        for u in urls[:5]:
            print(f"  {u}")
        return

    # ── Batch collect ──
    from acs.adapter import acs_shadow_collect
    results = {"total": len(urls), "success": 0, "failed": 0, "entries": []}

    for i, url in enumerate(urls):
        if i > 0:
            time.sleep(args.rate_limit)
        entry = {
            "url": url, "index": i + 1,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "status": "pending",
        }
        try:
            print(f"[{i+1}/{len(urls)}] {url[:80]}...", end=" ", flush=True)
            html = fetch_html(url, timeout=args.timeout)
            legacy = {"title": "", "body": html[:200], "error": ""}
            shadow_result = acs_shadow_collect(
                url=url, html=html, legacy_record=legacy, fetch_quality="full",
            )
            entry["status"] = "ok"
            entry["html_size"] = len(html)
            results["success"] += 1
            print("OK")
        except urllib.error.HTTPError as e:
            entry["status"] = "http_error"
            entry["error"] = f"HTTP {e.code}"
            results["failed"] += 1
            print(f"FAIL ({e.code})")
        except Exception as e:
            entry["status"] = "error"
            entry["error"] = str(e)[:200]
            results["failed"] += 1
            print(f"FAIL ({type(e).__name__})")

        results["entries"].append(entry)

    # ── Summary ──
    print(f"\nDone. {results['success']} ok, {results['failed']} failed out of {results['total']}")
    out_path = f"acs_shadow_logs/batch_{time.strftime('%Y%m%d-%H%M%S')}.json"
    os.makedirs("acs_shadow_logs", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"Batch summary: {out_path}")
    print(f"Shadow records: acs_shadow_logs/acs_shadow.jsonl")


if __name__ == "__main__":
    main()
