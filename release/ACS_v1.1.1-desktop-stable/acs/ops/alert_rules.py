"""Alert rules."""
from dataclasses import dataclass, field
from typing import List

@dataclass
class Alert:
    rule:str=""; severity:str="info"; message:str=""; value:float=0.0; threshold:float=0.0; triggered:bool=False
    def to_dict(self): return {"rule":self.rule,"severity":self.severity,"message":self.message,"value":self.value,"threshold":self.threshold,"triggered":self.triggered}

class AlertEngine:
    def __init__(self): self.rules=[]
    def check(self,metrics:dict)->List[Alert]:
        a=[]
        r=metrics.get("ai_fail_rate",0)
        if r>0.3: a.append(Alert("ai_fail_rate","high",f"AI fail rate {r:.1%}",r,0.3,True))
        c=metrics.get("cost_ratio",0)
        if c>0.8: a.append(Alert("cost_near_limit","high",f"Cost {c:.0%} of limit",c,0.8,True))
        s=metrics.get("shadow_success_rate",1)
        if s<0.5: a.append(Alert("shadow_success_drop","high",f"Shadow success {s:.1%}",s,0.5,True))
        sf=metrics.get("selector_fail_rate",0)
        if sf>0.3: a.append(Alert("selector_fail","medium",f"Selector fail {sf:.1%}",sf,0.3,True))
        pr=metrics.get("pending_reviews",0)
        if pr>20: a.append(Alert("pending_backlog","medium",f"Pending reviews: {pr}",pr,20,True))
        return a
