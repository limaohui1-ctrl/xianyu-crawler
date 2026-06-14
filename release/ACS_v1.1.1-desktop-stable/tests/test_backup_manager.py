"""Tests for backup manager."""
import sys, os, tempfile, shutil, pytest, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.ops.backup_manager import backup

def test_backup_dry_run():
    r = backup(target_dir=os.path.join(tempfile.mkdtemp(), "backups"), dry_run=True)
    assert r["dry_run"] is True
    assert len(r["items"]) >= 1

def test_backup_execute():
    d = tempfile.mkdtemp()
    try:
        src_dir = os.path.join(d, "test_data")
        os.makedirs(src_dir)
        with open(os.path.join(src_dir, "data.json"), "w") as f: f.write("test")
        r = backup(target_dir=os.path.join(d, "backups"), dry_run=False)
        assert r["dry_run"] is False
        assert os.path.exists(r["target"])
    finally: shutil.rmtree(d, ignore_errors=True)

def test_backup_excludes_env():
    r = backup(target_dir=os.path.join(tempfile.mkdtemp(), "backups"), dry_run=True)
    for item in r["items"]:
        assert ".env" not in item.get("source", "")

def test_backup_items_have_source():
    r = backup(dry_run=True)
    for item in r["items"]:
        assert "source" in item
        assert "status" in item
