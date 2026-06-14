"""Weekly report."""
import json, time
from dataclasses import dataclass, asdict

@dataclass
class WeeklyReport:
    week_start:str=""; week_end:str=""
    total_shadow:int=0; avg_success_rate:float=0.0
    total_ai_calls:int=0; total_ai_cost:float=0.0; total_errors:int=0
    structure_changes:int=0; reviews_opened:int=0; reviews_closed:int=0
    risk_items:list=None
    def __post_init__(self):
        if self.risk_items is None: self.risk_items=[]
        if not self.week_start: self.week_start=time.strftime("%Y-%m-%d")
    def markdown(self):
        w=self
        return f"""# Weekly Report {w.week_start} to {w.week_end}\n\n| Metric | Value |\n| ------ | ----- |\n| Shadow | {w.total_shadow} |\n| Success | {w.avg_success_rate:.1%} |\n| AI calls | {w.total_ai_calls} |\n| AI cost | ${w.total_ai_cost:.6f} |\n| Errors | {w.total_errors} |\n| Structure | {w.structure_changes} |\n| Opened | {w.reviews_opened} |\n| Closed | {w.reviews_closed} |\n\n> ACS_MODE=shadow. No auto-apply.\n"""
    def to_dict(self): return asdict(self)

def generate_weekly(dailies=None):
    r=WeeklyReport()
    if dailies:
        r.total_shadow=sum(d.shadow_entries for d in dailies)
        r.total_ai_calls=sum(d.ai_calls for d in dailies)
        r.total_ai_cost=sum(d.ai_cost for d in dailies)
        r.total_errors=sum(d.errors for d in dailies)
        r.reviews_opened=sum(d.new_reviews for d in dailies)
        r.reviews_closed=sum(d.reviews_processed for d in dailies)
        rates=[d.shadow_success_rate for d in dailies if d.shadow_success_rate>0]
        if rates: r.avg_success_rate=sum(rates)/len(rates)
    return r
