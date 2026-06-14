"""Per-site metrics aggregation."""
import os, json
from typing import Dict, List

class SiteMetrics:
    def __init__(self, shadow_log="acs_shadow_logs/acs_shadow.jsonl"):
        self.shadow_log = shadow_log

    def get_all_entries(self) -> List[dict]:
        entries = []
        if not os.path.exists(self.shadow_log): return entries
        with open(self.shadow_log, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line: continue
                try:
                    entries.append(json.loads(line))
                except Exception:  # skip malformed metrics lines
                    pass
        return entries

    def site_summary(self, site_id: str) -> dict:
        entries = self.get_all_entries()
        site_entries = [e for e in entries if site_id in (e.get("url", "") or "")]
        total = len(site_entries)
        if total == 0:
            return {"site_id": site_id, "total": 0, "success_rate": 0, "avg_completeness": 0}
        successes = sum(1 for e in site_entries if e.get("acs_success"))
        comp_sum = sum(e.get("acs_completeness", 0) for e in site_entries)
        return {
            "site_id": site_id,
            "total": total,
            "success_rate": successes / max(total, 1),
            "avg_completeness": comp_sum / max(total, 1),
        }

    def all_summaries(self) -> List[dict]:
        entries = self.get_all_entries()
        from urllib.parse import urlparse
        sites: Dict[str, list] = {}
        for e in entries:
            url = e.get("url", "")
            try:
                domain = urlparse(url).netloc or url[:50]
            except:
                domain = url[:50]
            sites.setdefault(domain, []).append(e)
        result = []
        for domain, site_entries in sites.items():
            total = len(site_entries)
            successes = sum(1 for e in site_entries if e.get("acs_success"))
            comp_sum = sum(e.get("acs_completeness", 0) for e in site_entries)
            result.append({
                "site_id": domain,
                "total": total,
                "success_rate": successes / max(total, 1),
                "avg_completeness": comp_sum / max(total, 1),
            })
        return result
