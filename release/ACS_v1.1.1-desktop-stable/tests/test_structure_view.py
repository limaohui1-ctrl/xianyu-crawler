"""Tests for acs.dashboard.structure_view — structure history display."""
import sys, os, tempfile, shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
from acs.storage.structure_history_store import StructureHistoryStore
from acs.dashboard.structure_view import StructureView

@pytest.fixture
def view():
    d = tempfile.mkdtemp()
    store = StructureHistoryStore(db_path=os.path.join(d, "history.db"))
    v = StructureView(store)
    yield v
    store.close()
    shutil.rmtree(d, ignore_errors=True)

class TestStructureView:
    def test_get_summary(self, view):
        view.store.save_snapshot("s", "u", dom_node_count=10)
        s = view.get_summary()
        assert s["total_snapshots"] == 1
        assert s["unique_sites"] == 1

    def test_get_recent(self, view):
        view.store.save_snapshot("s", "u1", dom_node_count=5)
        view.store.save_snapshot("s", "u2", dom_node_count=10)
        recent = view.get_recent("s", limit=5)
        assert len(recent) == 2

    def test_get_site_stats(self, view):
        view.store.save_snapshot("s", "u1", change_score=0.2)
        view.store.save_snapshot("s", "u2", change_score=0.4)
        ss = view.get_site_stats("s")
        assert ss["total_snapshots"] == 2

    def test_markdown(self, view):
        view.store.save_snapshot("s", "http://x.com", dom_node_count=42, change_score=0.1)
        md = view.markdown(site_id="s")
        assert "Structure Change History" in md
        assert "42" in md

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
