"""Daily report."""
import json, time
from dataclasses import dataclass, asdict

@dataclass
class DailyReport:
    date:str=""; shadow_entries:int=0; shadow_success_rate:float=0.0
    ai_calls:int=0; ai_tokens:int=0; ai_cost:float=0.0; errors:int=0
    new_reviews:int=0; reviews_processed:int=0; alerts:list=None
    def __post_init__(self):
        if self.alerts is None: self.alerts=[]
        if not self.date: self.date=time.strftime("%Y-%m-%d")
    def markdown(self):
        s=self
        return f"""# Daily Report {s.date}\n\n| Metric | Value |\n| ------ | ----- |\n| Shadow | {s.shadow_entries} |\n| Success | {s.shadow_success_rate:.1%} |\n| AI calls | {s.ai_calls} |\n| AI tokens | {s.ai_tokens:,} |\n| AI cost | ${s.ai_cost:.6f} |\n| Errors | {s.errors} |\n| New reviews | {s.new_reviews} |\n| Processed | {s.reviews_processed} |\n\n> ACS_MODE=shadow. No auto-apply.\n"""
    def to_dict(self): return asdict(self)

def generate_daily(shadow=None,cost=None,reviews=None,audit=None):
    r=DailyReport()
    if shadow: r.shadow_entries=shadow.get("total_entries",0); r.shadow_success_rate=shadow.get("acs_success_rate",0)
    if cost: r.ai_calls=cost.get("total_ai_calls",0); r.ai_tokens=cost.get("total_tokens",0); r.ai_cost=cost.get("estimated_cost",0)
    if reviews:
        by=reviews.get("by_status",{}); r.new_reviews=by.get("pending_review",0)
        r.reviews_processed=by.get("approved",0)+by.get("rejected",0)
    if audit: r.errors=audit.get("failed_calls",0)
    return r
