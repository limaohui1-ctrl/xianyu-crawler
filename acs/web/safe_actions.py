"""Safe review actions."""
import os, time
from acs.review.pending_review import PendingReviewManager
from acs.review.review_decision import ReviewDecision, DecisionLog
from acs.storage.repair_review_store import RepairReviewStore

DB=os.path.join("acs_data","reviews.db")

class SafeActionManager:
    def __init__(self,db_path=None):
        self.store=RepairReviewStore(db_path or DB)
        self.mgr=PendingReviewManager(self.store)
        self.decisions=DecisionLog()
    def approve(self,rid,note=""):
        ok=self.mgr.approve(rid,note);self.decisions.record(ReviewDecision(rid,"approved",note=note))
        return {"success":ok,"action":"approved","review_id":rid}
    def reject(self,rid,note=""):
        ok=self.mgr.reject(rid,note);self.decisions.record(ReviewDecision(rid,"rejected",note=note))
        return {"success":ok,"action":"rejected","review_id":rid}
    def needs_more_data(self,rid,note=""):
        ok=self.mgr.request_more_data(rid,note);self.decisions.record(ReviewDecision(rid,"needs_more_data",note=note))
        return {"success":ok,"action":"needs_more_data","review_id":rid}
    def archive(self,rid):
        ok=self.mgr.archive(rid);self.decisions.record(ReviewDecision(rid,"archived"))
        return {"success":ok,"action":"archived","review_id":rid}
    def get_stats(self): return self.mgr.get_stats()
    def get_pending(self,limit=50): return [i.to_dict() for i in self.mgr.get_pending(limit=limit)]
    def get_audit(self,limit=100): return self.decisions.to_list()[-limit:]
