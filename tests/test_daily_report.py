"""Tests for daily report generator."""
import sys, os, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.ops.daily_report import DailyReport, generate_daily

def test_generate_empty():
    r = generate_daily()
    assert r.shadow_entries == 0
    assert r.ai_calls == 0

def test_generate_with_data():
    r = generate_daily(
        shadow={"total_entries": 10, "acs_success_rate": 0.85},
        cost={"total_ai_calls": 5, "total_tokens": 1000, "estimated_cost": 0.01},
        reviews={"by_status": {"pending_review": 3, "approved": 2, "rejected": 1}},
        audit={"failed_calls": 1}
    )
    assert r.shadow_entries == 10
    assert r.ai_calls == 5
    assert r.ai_cost == 0.01
    assert r.new_reviews == 3
    assert r.reviews_processed == 3
    assert r.errors == 1

def test_markdown():
    r = DailyReport(shadow_entries=5, ai_calls=2, ai_cost=0.001)
    md = r.markdown()
    assert "Daily Report" in md
    assert "Shadow" in md.lower() or "shadow" in md.lower()
    assert "0.001" in md

def test_to_dict():
    r = DailyReport(shadow_entries=3)
    d = r.to_dict()
    assert d["shadow_entries"] == 3
