"""Manual approval gate — human approval required before canary.

States: pending -> approved -> expired/revoked, or pending -> rejected.
NEVER auto-switches ACS_MODE.
"""
import os, json, time
from dataclasses import dataclass, asdict
from typing import List, Optional

DB_PATH = "acs_data/approvals.db"

@dataclass
class ApprovalRecord:
    approval_id: str = ""
    site_id: str = ""
    reviewer: str = ""
    decision: str = "pending"
    note: str = ""
    created_at: str = ""
    reviewed_at: str = ""
    expires_at: str = ""

    def __post_init__(self):
        if not self.created_at: self.created_at = time.strftime("%Y-%m-%dT%H:%M:%S")

    def to_dict(self):
        return asdict(self)

    def is_valid(self) -> bool:
        if self.decision != "approved": return False
        if self.expires_at:
            try:
                exp = time.mktime(time.strptime(self.expires_at, "%Y-%m-%dT%H:%M:%S"))
                if time.time() > exp: return False
            except: pass
        return True

class ApprovalGate:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or DB_PATH
        self._records: List[ApprovalRecord] = []
        self._load()

    def _load(self):
        if os.path.exists(self.db_path):
            try:
                with open(self.db_path, encoding="utf-8") as f:
                    data = json.load(f)
                self._records = [ApprovalRecord(**item) for item in data]
            except: pass

    def _save(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with open(self.db_path, "w", encoding="utf-8") as f:
            json.dump([r.to_dict() for r in self._records], f, ensure_ascii=False, indent=2)

    def submit(self, site_id: str, reviewer: str = "", note: str = "", expires_days: int = 7) -> ApprovalRecord:
        rid = f"approval_{int(time.time()*1000)}"
        exp = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() + expires_days*86400))
        r = ApprovalRecord(approval_id=rid, site_id=site_id, reviewer=reviewer, decision="pending", note=note, expires_at=exp)
        self._records.append(r)
        self._save()
        return r

    def approve(self, approval_id: str, reviewer: str = "", note: str = "") -> bool:
        for r in self._records:
            if r.approval_id == approval_id:
                r.decision = "approved"; r.reviewer = reviewer; r.note = note; r.reviewed_at = time.strftime("%Y-%m-%dT%H:%M:%S")
                self._save(); return True
        return False

    def reject(self, approval_id: str, reviewer: str = "", note: str = "") -> bool:
        for r in self._records:
            if r.approval_id == approval_id:
                r.decision = "rejected"; r.reviewer = reviewer; r.note = note; r.reviewed_at = time.strftime("%Y-%m-%dT%H:%M:%S")
                self._save(); return True
        return False

    def revoke(self, approval_id: str) -> bool:
        for r in self._records:
            if r.approval_id == approval_id:
                r.decision = "revoked"; r.reviewed_at = time.strftime("%Y-%m-%dT%H:%M:%S")
                self._save(); return True
        return False

    def get_latest(self, site_id: str) -> Optional[ApprovalRecord]:
        for r in reversed(self._records):
            if r.site_id == site_id: return r
        return None

    def is_ready_for_canary(self, site_id: str) -> bool:
        latest = self.get_latest(site_id)
        if not latest: return False
        return latest.is_valid()

    def all_for_site(self, site_id: str) -> List[ApprovalRecord]:
        return [r for r in self._records if r.site_id == site_id]

    def to_list(self) -> list:
        return [r.to_dict() for r in self._records]
