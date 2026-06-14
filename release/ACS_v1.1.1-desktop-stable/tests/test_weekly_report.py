"""Tests for weekly report generator."""
import sys, os, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.ops.weekly_report import WeeklyReport, generate_weekly
from acs.ops.daily_report import DailyReport

def test_generate_empty():
    r = generate_weekly()
    assert r.total_shadow == 0

def test_generate_from_dailies():
    d1 = DailyReport(shadow_entries=10, ai_calls=3, ai_cost=0.01, errors=1, new_reviews=2, reviews_processed=1, shadow_success_rate=0.8)
    d2 = DailyReport(shadow_entries=15, ai_calls=5, ai_cost=0.02, errors=0, new_reviews=1, reviews_processed=2, shadow_success_rate=0.9)
    r = generate_weekly(dailies=[d1, d2])
    assert r.total_shadow == 25
    assert r.total_ai_calls == 8
    assert r.total_ai_cost == 0.03
    assert r.total_errors == 1
    assert r.reviews_opened == 3
    assert r.reviews_closed == 3
    assert 0.84 < r.avg_success_rate < 0.86

def test_markdown():
    r = WeeklyReport(total_shadow=20, total_ai_calls=5, total_ai_cost=0.005)
    md = r.markdown()
    assert "Weekly Report" in md
    assert "20" in md

def test_to_dict():
    r = WeeklyReport(total_shadow=10)
    d = r.to_dict()
    assert d["total_shadow"] == 10
