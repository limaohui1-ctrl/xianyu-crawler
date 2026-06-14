"""Tests for scheduler — daily, weekly, cron export, Windows task, dry-run."""
import sys, os, pytest, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.ops.scheduler import generate_and_save, export_cron, export_windows_task, next_run_time

def test_daily_generation():
    r = generate_and_save("daily")
    assert r["report_type"] == "daily"
    assert os.path.exists(r["markdown"])
    assert os.path.exists(r["json"])

def test_weekly_generation():
    r = generate_and_save("weekly")
    assert r["report_type"] == "weekly"
    assert os.path.exists(r["markdown"])

def test_export_cron():
    r = export_cron()
    assert "daily_cron" in r
    assert "weekly_cron" in r
    assert "daily_command" in r
    assert "next_daily_run" in r
    # Verify cron format: minute hour * * * / minute hour * * day
    import re
    assert re.match(r"\d+ \d+ \* \* \*", r["daily_cron"])
    assert re.match(r"\d+ \d+ \* \* \d", r["weekly_cron"])

def test_export_cron_custom_time():
    r = export_cron(daily_time="06:30", weekly_time="10:00", weekly_day="friday")
    assert r["daily_cron"].startswith("30 6")
    assert r["weekly_cron"].startswith("0 10")
    assert r["weekly_crontab"].count("friday") == 0  # uses numeric

def test_export_windows_task():
    r = export_windows_task()
    assert "daily_schtasks" in r
    assert "weekly_schtasks" in r
    assert "schtasks" in r["daily_schtasks"].lower()
    assert "schtasks" in r["weekly_schtasks"].lower()

def test_dry_run_daily():
    # Simulate dry-run via import
    import acs.ops.scheduler as s
    r = s.next_run_time(8, 0)
    assert "T" in r  # ISO format

def test_dry_run_weekly():
    r = next_run_time(9, 0, weekday=0)
    assert "T" in r

def test_no_key_leak_in_cron_export():
    r = export_cron()
    j = json.dumps(r)
    assert "sk-" not in j
    assert "Bearer" not in j

def test_no_key_leak_in_windows_export():
    r = export_windows_task()
    j = json.dumps(r)
    assert "sk-" not in j
    assert "Bearer" not in j
