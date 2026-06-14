"""Tests for acs.storage.repair_review_store — submit/query/review status transitions."""
import sys, os, tempfile, shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
from acs.storage.repair_review_store import RepairReviewStore

@pytest.fixture
def store():
    d = tempfile.mkdtemp()
    s = RepairReviewStore(db_path=os.path.join(d, "reviews.db"))
    yield s
    s.close()
    shutil.rmtree(d, ignore_errors=True)

class TestRepairReviewStore:
    def test_submit_and_get(self, store):
        rid = store.submit("test_site", "http://x.com", "title", "h1.old", "h1.new", 0.85, "evidence text")
        assert rid > 0
        item = store.get_by_id(rid)
        assert item["review_status"] == "pending_review"
        assert item["confidence"] == 0.85

    def test_get_pending(self, store):
        store.submit("s1", "u1", "title", "old", "new1", 0.9)
        store.submit("s1", "u2", "price", "old2", "new2", 0.7)
        pending = store.get_pending(site_id="s1")
        assert len(pending) == 2

    def test_get_pending_by_field(self, store):
        store.submit("s", "u", "title", "a", "b", 0.5)
        store.submit("s", "u", "price", "c", "d", 0.5)
        p = store.get_pending(field_name="title")
        assert len(p) == 1

    def test_update_review_approved(self, store):
        rid = store.submit("s", "u", "t", "a", "b", 0.8)
        assert store.update_review(rid, "approved", "Looks good")
        item = store.get_by_id(rid)
        assert item["review_status"] == "approved"
        assert item["reviewer_note"] == "Looks good"

    def test_update_review_rejected(self, store):
        rid = store.submit("s", "u", "t", "a", "b", 0.8)
        store.update_review(rid, "rejected", "Doesn't match")
        assert store.get_by_id(rid)["review_status"] == "rejected"

    def test_update_review_needs_more_data(self, store):
        rid = store.submit("s", "u", "t", "a", "b", 0.3)
        store.update_review(rid, "needs_more_data")
        assert store.get_by_id(rid)["review_status"] == "needs_more_data"

    def test_invalid_status_rejected(self, store):
        rid = store.submit("s", "u", "t", "a", "b", 0.5)
        assert not store.update_review(rid, "invalid_status")

    def test_get_approved(self, store):
        rid = store.submit("s", "u", "t", "a", "b", 0.9)
        store.update_review(rid, "approved")
        approved = store.get_approved(site_id="s")
        assert len(approved) == 1

    def test_get_by_status(self, store):
        store.submit("s", "u1", "t", "a", "b", 0.8)
        store.submit("s", "u2", "t", "a", "b", 0.8)
        pending = store.get_by_status("pending_review")
        assert len(pending) == 2

    def test_submit_batch(self, store):
        candidates = [
            {"site_id": "s", "url": "u1", "field_name": "t", "old_selector": "a", "candidate_selector": "b", "confidence": 0.8},
            {"site_id": "s", "url": "u2", "field_name": "p", "old_selector": "c", "candidate_selector": "d", "confidence": 0.7},
        ]
        count = store.submit_batch(candidates)
        assert count == 2

    def test_stats(self, store):
        store.submit("s", "u", "t", "a", "b", 0.5)
        s = store.get_stats()
        assert s["total"] == 1
        assert s["by_status"]["pending_review"] == 1

    def test_clear(self, store):
        store.submit("s", "u", "t", "a", "b", 0.5)
        store.clear()
        assert store.get_stats()["total"] == 0

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
