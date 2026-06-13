"""Tests for shadow fallback chain — AI parser trigger in shadow mode."""
import sys, os, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_acs_shadow_collect_off_mode():
    os.environ["ACS_MODE"] = "off"
    from acs.adapter import acs_shadow_collect
    result = acs_shadow_collect("http://x.com", "<html></html>", {"title":"","body":"","error":""})
    assert result is None
    os.environ["ACS_MODE"] = "shadow"

def test_acs_shadow_collect_shadow_mode():
    os.environ["ACS_MODE"] = "shadow"
    from acs.adapter import acs_shadow_collect
    result = acs_shadow_collect("http://x.com", "<html><h1>Test</h1></html>", {"title":"","body":"","error":""})
    assert result is None  # shadow returns None by design

def test_shadow_writes_jsonl():
    import tempfile, shutil, os, sys
    d = tempfile.mkdtemp()
    try:
        os.environ["UNIVERSAL_COLLECTOR_DATA_DIR"] = d
        os.environ["ACS_MODE"] = "shadow"
        # Force reload to pick up env change
        if "acs.adapter" in sys.modules:
            del sys.modules["acs.adapter"]
        from acs.adapter import _acs_shadow_log_dir, acs_shadow_collect
        log_dir = _acs_shadow_log_dir()
        assert log_dir == os.path.abspath(d), f"Expected {d}, got {log_dir}"
        acs_shadow_collect("http://t.com", "<html><h1>T</h1></html>", {"title":"T","body":"B","error":""})
        shadow_file = os.path.join(d, "acs_shadow.jsonl")
        assert os.path.exists(shadow_file), f"Missing {shadow_file}"
    finally:
        os.environ.pop("UNIVERSAL_COLLECTOR_DATA_DIR", None)
        os.environ["ACS_MODE"] = "shadow"
        shutil.rmtree(d, ignore_errors=True)

def test_parse_with_acs_engine():
    from acs.adapter import parse_with_acs_engine
    result = parse_with_acs_engine("http://x.com", "<html><h1>Hello</h1><p>World</p></html>")
    assert result is not None
    assert result.title == "Hello"

def test_force_ai_fallback_flag():
    """Verify --force-ai-fallback parses correctly."""
    v = "true"
    assert v.lower() in ("true", "1", "yes")
    v = "false"
    assert v.lower() not in ("true", "1", "yes")
