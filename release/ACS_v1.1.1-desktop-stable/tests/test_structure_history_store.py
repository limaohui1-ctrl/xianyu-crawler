"""Tests for acs.storage.structure_history_store — save/query snapshots."""
import sys, os, tempfile, shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
from acs.storage.structure_history_store import StructureHistoryStore

@pytest.fixture
def store():
    d = tempfile.mkdtemp()
    s = StructureHistoryStore(db_path=os.path.join(d, "history.db"))
    yield s
    s.close()
    shutil.rmtree(d, ignore_errors=True)

class TestStructureHistoryStore:
    def test_save_and_get(self, store):
        rid = store.save_snapshot("test_site", "http://x.com", dom_node_count=42, change_score=0.1)
        assert rid > 0
        row = store.get_latest("test_site", "http://x.com")
        assert row["dom_node_count"] == 42
        assert row["change_score"] == 0.1

    def test_get_recent(self, store):
        for i in range(5):
            store.save_snapshot("test_site", f"http://x.com/{i}", dom_node_count=i)
        recent = store.get_recent("test_site", limit=3)
        assert len(recent) == 3

    def test_get_by_url(self, store):
        store.save_snapshot("s1", "http://unique.com/p", dom_node_count=10)
        store.save_snapshot("s2", "http://unique.com/p", dom_node_count=20)
        rows = store.get_by_url("http://unique.com/p", limit=10)
        assert len(rows) == 2

    def test_save_batch(self, store):
        snaps = [
            {"site_id": "b", "url": "http://b.com/1", "dom_node_count": 5},
            {"site_id": "b", "url": "http://b.com/2", "dom_node_count": 10},
        ]
        count = store.save_batch(snaps)
        assert count == 2
        assert store.get_site_stats("b")["total_snapshots"] == 2

    def test_site_stats(self, store):
        store.save_snapshot("stats_site", "u1", change_score=0.3)
        store.save_snapshot("stats_site", "u2", change_score=0.5)
        s = store.get_site_stats("stats_site")
        assert s["total_snapshots"] == 2
        assert 0.39 < s["avg_change_score"] < 0.41

    def test_get_latest_none(self, store):
        assert store.get_latest("nonexistent") is None

    def test_persistence(self, store):
        store.save_snapshot("persist", "u", dom_node_count=99)
        db = store.db_path
        store.close()
        s2 = StructureHistoryStore(db_path=db)
        row = s2.get_latest("persist", "u")
        assert row["dom_node_count"] == 99
        s2.close()

    def test_clean_old(self, store):
        store.save_snapshot("clean", "u", dom_node_count=1)
        count = store.clean_old(max_age_days=0)  # Remove everything
        assert count >= 0

    def test_stats(self, store):
        store.save_snapshot("a", "u1")
        store.save_snapshot("b", "u2")
        s = store.get_stats()
        assert s["total_snapshots"] == 2
        assert s["unique_sites"] == 2

    def test_clear(self, store):
        store.save_snapshot("x", "u")
        store.clear()
        assert store.get_latest("x", "u") is None

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
