"""Tests for log rotation."""
import sys, os, tempfile, shutil, pytest, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.ops.log_rotation import rotate_log, rotate_logs

def test_rotate_dry_run():
    d = tempfile.mkdtemp()
    try:
        src = os.path.join(d, "test.jsonl")
        with open(src, "w") as f: f.write("data")
        r = rotate_log(src, archive_dir=os.path.join(d, "archive"), dry_run=True)
        assert r["status"] == "dry_run"
        assert r["size"] > 0
    finally: shutil.rmtree(d, ignore_errors=True)

def test_rotate_execute():
    d = tempfile.mkdtemp()
    try:
        src = os.path.join(d, "test.jsonl")
        with open(src, "w") as f: f.write("hello")
        r = rotate_log(src, archive_dir=os.path.join(d, "archive"), dry_run=False)
        assert r["status"] == "archived"
        assert os.path.exists(r["destination"])
    finally: shutil.rmtree(d, ignore_errors=True)

def test_rotate_forbidden_py():
    r = rotate_log("test_protected.py", dry_run=True)
    assert r["status"] in ("forbidden", "skipped")

def test_rotate_missing():
    r = rotate_log("nonexistent_file_12345.jsonl", dry_run=True)
    assert r["status"] == "skipped"

def test_rotate_logs_batch():
    d = tempfile.mkdtemp()
    try:
        f1 = os.path.join(d, "a.jsonl")
        f2 = os.path.join(d, "b.jsonl")
        with open(f1, "w") as f: f.write("x")
        with open(f2, "w") as f: f.write("y")
        results = rotate_logs([f1, f2], archive_dir=os.path.join(d, "archive"), dry_run=True)
        assert len(results) == 2
    finally: shutil.rmtree(d, ignore_errors=True)
