"""Tests for acs.review.pending_review — review manager, workflow enforcement."""
import sys, os, tempfile, shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
from acs.review.pending_review import PendingReviewManager, ReviewItem
from acs.review.review_decision import ReviewDecision, DecisionLog, ReviewAction
from acs.review.review_exporter import ReviewExporter
from acs.storage.repair_review_store import RepairReviewStore

@pytest.fixture
def mgr():
    d = tempfile.mkdtemp()
    store = RepairReviewStore(db_path=os.path.join(d, "reviews.db"))
    m = PendingReviewManager(store)
    yield m
    store.close()
    shutil.rmtree(d, ignore_errors=True)

class TestPendingReviewManager:
    def test_submit_creates_pending(self, mgr):
        rid = mgr.submit("s", "u", "title", "h1.old", "h1.new", 0.9, "evidence")
        item = mgr.get_by_id(rid)
        assert item.review_status == "pending_review"

    def test_approve(self, mgr):
        rid = mgr.submit("s", "u", "t", "a", "b", 0.9)
        assert mgr.approve(rid, "ok")
        item = mgr.get_by_id(rid)
        assert item.review_status == "approved"

    def test_reject(self, mgr):
        rid = mgr.submit("s", "u", "t", "a", "b", 0.9)
        assert mgr.reject(rid, "no")
        assert mgr.get_by_id(rid).review_status == "rejected"

    def test_request_more_data(self, mgr):
        rid = mgr.submit("s", "u", "t", "a", "b", 0.3)
        assert mgr.request_more_data(rid)
        assert mgr.get_by_id(rid).review_status == "needs_more_data"

    def test_archive(self, mgr):
        rid = mgr.submit("s", "u", "t", "a", "b", 0.5)
        assert mgr.archive(rid)
        assert mgr.get_by_id(rid).review_status == "archived"

    def test_cannot_approve_archived(self, mgr):
        rid = mgr.submit("s", "u", "t", "a", "b", 0.5)
        mgr.archive(rid)
        assert not mgr.approve(rid)

    def test_invalid_status_fails(self, mgr):
        rid = mgr.submit("s", "u", "t", "a", "b", 0.5)
        assert not mgr.store.update_review(rid, "bad_status")

    def test_approved_not_auto_applied(self, mgr):
        rid = mgr.submit("s", "u", "t", "a", "b", 0.95)
        mgr.approve(rid)
        item = mgr.get_by_id(rid)
        # Verify there's no "applied" flag anywhere
        assert item.review_status == "approved"
        assert "auto_applied" not in item.to_dict().get("auto_applied", "") or not item.to_dict().get("auto_applied")

    def test_get_pending(self, mgr):
        mgr.submit("s", "u1", "t", "a", "b", 0.8)
        mgr.submit("s", "u2", "t", "a", "b", 0.7)
        pending = mgr.get_pending(site_id="s")
        assert len(pending) == 2

    def test_get_approved(self, mgr):
        rid = mgr.submit("s", "u", "t", "a", "b", 0.9)
        mgr.approve(rid)
        approved = mgr.get_approved(site_id="s")
        assert len(approved) == 1

    def test_audit_log(self, mgr):
        rid = mgr.submit("s", "u", "t", "a", "b", 0.9)
        mgr.approve(rid)
        log = mgr.audit_log
        assert len(log) >= 2
        assert log[0]["action"] == "submit"

    def test_approve_above_confidence(self, mgr):
        mgr.submit("s", "u1", "t", "a", "b1", 0.95)
        mgr.submit("s", "u2", "t", "a", "b2", 0.60)
        count = mgr.approve_above_confidence("s", threshold=0.9)
        assert count == 1

    def test_get_nonexistent(self, mgr):
        assert mgr.get_by_id(99999) is None

    def test_get_stats(self, mgr):
        mgr.submit("s", "u", "t", "a", "b", 0.5)
        s = mgr.get_stats()
        assert s["total"] == 1

class TestReviewDecision:
    def test_decision_to_dict(self):
        d = ReviewDecision(review_id=1, action="approved", reviewer="test")
        dd = d.to_dict()
        assert dd["action"] == "approved"
        assert dd["auto_applied"] is False

    def test_decision_log_stats(self):
        log = DecisionLog()
        log.record(ReviewDecision(1, "approved"))
        log.record(ReviewDecision(2, "rejected"))
        s = log.get_stats()
        assert s["total_decisions"] == 2

class TestReviewExporter:
    def test_export_json(self, mgr):
        mgr.submit("s", "u", "t", "a", "b", 0.8)
        ex = ReviewExporter(mgr)
        j = ex.export_json()
        assert "pending_review" in j

    def test_export_csv(self, mgr):
        mgr.submit("s", "u", "t", "a", "b", 0.8)
        ex = ReviewExporter(mgr)
        c = ex.export_csv()
        assert "pending_review" in c or "id,site_id" in c

    def test_export_markdown(self, mgr):
        mgr.submit("s", "u", "t", "a", "b", 0.8)
        rid = mgr.submit("s", "u2", "t", "a", "b2", 0.9)
        mgr.approve(rid)
        ex = ReviewExporter(mgr)
        md = ex.export_markdown()
        assert "Pending Review" in md
        assert "Approved" in md

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
