"""Tests for data retention."""
import sys, os, tempfile, shutil, pytest, json, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.ops.data_retention import cleanup, list_old_files

def test_list_old_files_finds_old():
    d = tempfile.mkdtemp()
    try:
        old_file = os.path.join(d, "old.txt")
        with open(old_file, "w") as f: f.write("old")
        os.utime(old_file, (0, 0))
        old = list_old_files(d, max_age_days=0)
        found = any(os.path.basename(f.get("path","")) == "old.txt" for f in old)
        assert found
    finally: shutil.rmtree(d, ignore_errors=True)

def test_cleanup_dry_run_no_delete():
    d = tempfile.mkdtemp()
    try:
        f = os.path.join(d, "old.txt")
        with open(f, "w") as fh: fh.write("old")
        os.utime(f, (0, 0))
        r = cleanup(directories=[d], max_age_days=0, dry_run=True)
        assert r["dry_run"] is True
        assert os.path.exists(f)
    finally: shutil.rmtree(d, ignore_errors=True)

def test_forbidden_dirs():
    r = cleanup(directories=["acs"], max_age_days=0, dry_run=True)
    has_forbidden = any(e.get("status") == "forbidden" for e in r["entries"])
    assert has_forbidden

def test_dry_run_preserves_files():
    d = tempfile.mkdtemp()
    try:
        f = os.path.join(d, "old.txt")
        with open(f, "w") as fh: fh.write("old")
        os.utime(f, (0, 0))
        cleanup(directories=[d], max_age_days=0, dry_run=True)
        assert os.path.exists(f)
    finally: shutil.rmtree(d, ignore_errors=True)
