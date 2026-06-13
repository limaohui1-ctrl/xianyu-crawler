"""Tests for acs.observability.ai_call_audit — JSONL audit logging, API key safety."""
import sys, os, tempfile, shutil, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
from acs.observability.ai_call_audit import AICallAuditor, AICallRecord

@pytest.fixture
def auditor():
    d = tempfile.mkdtemp()
    a = AICallAuditor(log_path=os.path.join(d, "audit.jsonl"))
    yield a
    shutil.rmtree(d, ignore_errors=True)

class TestAICallAuditor:
    def test_log_call(self, auditor):
        r = auditor.log_call(url="http://x.com", tokens_prompt=100, tokens_completion=50, success=True)
        assert r.url == "http://x.com"
        assert r.success
        assert auditor.call_count == 1

    def test_log_call_failure(self, auditor):
        auditor.log_call(url="http://x.com", success=False, error="timeout")
        stats = auditor.get_stats()
        assert stats["failed_calls"] == 1

    def test_read_logs(self, auditor):
        auditor.log_call(url="http://a.com", tokens_prompt=10)
        auditor.log_call(url="http://b.com", tokens_prompt=20)
        entries = auditor.read_logs(limit=50)
        assert len(entries) == 2

    def test_no_api_key_in_record(self, auditor):
        r = auditor.log_call(url="http://x.com")
        d = r.to_dict()
        assert "api_key" not in d
        assert "key" not in d

    def test_stats(self, auditor):
        auditor.log_call(tokens_prompt=100, tokens_completion=50, success=True)
        auditor.log_call(tokens_prompt=200, tokens_completion=100, success=True)
        s = auditor.get_stats()
        assert s["total_calls"] == 2
        assert s["total_tokens"] == 450
        assert s["successful_calls"] == 2

    def test_log_call_from_response(self, auditor):
        class R: tokens = {"prompt": 10, "completion": 5}; error = ""
        r = auditor.log_call_from_response("id1", "http://x.com", "m", R())
        assert r.tokens_prompt == 10

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
