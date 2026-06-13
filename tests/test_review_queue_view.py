"""Tests for acs.dashboard.review_queue_view — queue display and status counts."""
import sys, os, tempfile, shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
from acs.storage.repair_review_store import RepairReviewStore
from acs.dashboard.review_queue_view import ReviewQueueView

@pytest.fixture
def view():
    d = tempfile.mkdtemp()
    store = RepairReviewStore(db_path=os.path.join(d, "reviews.db"))
    v = ReviewQueueView(store)
    yield v
    store.close()
    shutil.rmtree(d, ignore_errors=True)

class TestReviewQueueView:
    def test_get_summary_empty(self, view):
        s = view.get_summary()
        assert s["total"] == 0
        assert s["pending_review"] == 0

    def test_get_summary_with_data(self, view):
        view.store.submit("s", "u", "t", "a", "b", 0.9)
        s = view.get_summary()
        assert s["total"] == 1
        assert s["pending_review"] == 1

    def test_get_pending(self, view):
        view.store.submit("s", "u1", "t", "a", "b", 0.8)
        view.store.submit("s", "u2", "t", "a", "b", 0.7)
        pending = view.get_pending(site_id="s")
        assert len(pending) == 2

    def test_get_approved(self, view):
        rid = view.store.submit("s", "u", "t", "a", "b", 0.9)
        view.store.update_review(rid, "approved")
        approved = view.get_approved(site_id="s")
        assert len(approved) == 1

    def test_markdown(self, view):
        view.store.submit("s", "u", "t", "a", "b", 0.9)
        md = view.markdown()
        assert "Review Queue" in md
        assert "Pending" in md

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
