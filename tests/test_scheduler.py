"""Tests for scheduler."""
import sys, os, tempfile, shutil, pytest, json, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.ops.daily_report import DailyReport, generate_daily
from acs.ops.weekly_report import WeeklyReport, generate_weekly

def test_daily_report_generation():
    r = generate_daily(
        shadow={"total_entries": 5, "acs_success_rate": 0.8},
        cost={"total_ai_calls": 2, "total_tokens": 100, "estimated_cost": 0.001},
        reviews={"by_status": {"pending_review": 1, "approved": 0, "rejected": 0}},
        audit={"failed_calls": 0}
    )
    assert r.shadow_entries == 5
    assert r.ai_calls == 2
    assert r.date

def test_weekly_report_generation():
    d1 = DailyReport(shadow_entries=10, ai_calls=3, ai_cost=0.01,
                     errors=1, new_reviews=2, reviews_processed=1, shadow_success_rate=0.8)
    d2 = DailyReport(shadow_entries=15, ai_calls=5, ai_cost=0.02,
                     errors=0, new_reviews=1, reviews_processed=2, shadow_success_rate=0.9)
    r = generate_weekly(dailies=[d1, d2])
    assert r.total_shadow == 25
    assert r.total_ai_calls == 8
    assert r.total_ai_cost == 0.03

def test_scheduler_imports():
    import acs.ops.scheduler
    assert hasattr(acs.ops.scheduler, "generate_and_save")

def test_cron_export_imports():
    import acs.ops.cron_export
    assert hasattr(acs.ops.cron_export, "export_all")
