"""Tests for web dashboard data aggregation."""
import sys, os, pytest, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.dashboard.report_builder import ReportBuilder, DashboardReport

def test_report_builds():
    b = ReportBuilder()
    r = b.build()
    assert r.safety["auto_apply"] == False
    assert isinstance(r.to_dict(), dict)

def test_markdown_output():
    b = ReportBuilder()
    md = b.build_markdown()
    assert "ACS Dashboard Report" in md

def test_shadow_view():
    from acs.dashboard.shadow_view import ShadowView
    v = ShadowView(shadow_stats={"total_entries": 5, "acs_success_rate": 0.8, "ready_for_on_mode": False})
    s = v.get_summary()
    assert s["total_entries"] == 5
    md = v.markdown()
    assert "Shadow" in md

def test_cost_view():
    from acs.dashboard.cost_view import CostView
    from acs.observability.cost_report import CostReport
    cr = CostReport()
    cr.record_call(tokens_prompt=100, tokens_completion=50)
    v = CostView(cr)
    assert v.get_summary()["total_ai_calls"] == 1

def test_review_queue():
    import tempfile, shutil
    from acs.storage.repair_review_store import RepairReviewStore
    from acs.dashboard.review_queue_view import ReviewQueueView
    d = tempfile.mkdtemp()
    try:
        s = RepairReviewStore(db_path=os.path.join(d, "r.db"))
        s.submit("t", "u", "f", "a", "b", 0.8)
        v = ReviewQueueView(s)
        assert v.get_summary()["pending_review"] == 1
        assert "Review Queue" in v.markdown()
    finally:
        s.close(); shutil.rmtree(d, ignore_errors=True)

def test_structure_view():
    import tempfile, shutil
    from acs.storage.structure_history_store import StructureHistoryStore
    from acs.dashboard.structure_view import StructureView
    d = tempfile.mkdtemp()
    try:
        s = StructureHistoryStore(db_path=os.path.join(d, "h.db"))
        s.save_snapshot("x", "u", dom_node_count=10)
        v = StructureView(s)
        assert v.get_summary()["total_snapshots"] == 1
    finally:
        s.close(); shutil.rmtree(d, ignore_errors=True)
