"""Tests for acs.self_healing.failure_analyzer — failure classification."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
from acs.self_healing.failure_analyzer import FailureAnalyzer, FailureType, Severity

class TestFailureAnalyzer:
    def test_all_parsers_failed(self):
        fa = FailureAnalyzer()
        class FA: pass
        a1, a2 = FA(), FA()
        a1.success, a2.success = False, False
        a1.parser_name, a2.parser_name = "css", "fallback"
        a1.error, a2.error = "", ""
        r = fa.analyze(url="http://x.com", parse_attempts=[a1, a2])
        assert r.failure_type == FailureType.SELECTOR_FAILED
        assert r.recommend_ai_parser
        assert r.recommend_selector_repair

    def test_some_parser_succeeded_no_failure(self):
        fa = FailureAnalyzer()
        class FA: pass
        a1 = FA(); a1.success = True; a1.parser_name = "css"; a1.error = ""
        r = fa.analyze(url="http://x.com", parse_attempts=[a1])
        assert r.failure_type in (FailureType.UNKNOWN, FailureType.LOW_QUALITY_PARSE)

    def test_low_quality_with_missing_fields(self):
        fa = FailureAnalyzer(low_quality_threshold=50)
        class PR: pass
        pr = PR(); pr.completeness = 15; pr.missing_fields = ["title", "price"]; pr.error = ""
        r = fa.analyze(url="http://x.com", parse_result=pr)
        assert r.failure_type == FailureType.LOW_QUALITY_PARSE
        assert r.recommend_ai_parser

    def test_low_quality_no_missing_no_ai(self):
        fa = FailureAnalyzer(low_quality_threshold=50)
        class PR: pass
        pr = PR(); pr.completeness = 15; pr.missing_fields = []; pr.error = ""
        r = fa.analyze(url="http://x.com", parse_result=pr)
        assert r.failure_type == FailureType.LOW_QUALITY_PARSE
        assert not r.recommend_ai_parser

    def test_consecutive_field_failures(self):
        fa = FailureAnalyzer(missing_field_threshold=3)
        class PR: pass
        pr = PR(); pr.completeness = 60; pr.missing_fields = []; pr.error = ""
        r = fa.analyze(url="http://x.com", parse_result=pr, consecutive_field_failures=5)
        assert r.failure_type == FailureType.FIELD_MISSING
        assert r.recommend_ai_parser

    def test_http_error_classification(self):
        fa = FailureAnalyzer()
        class ER: pass
        e = ER(); e.category = "network_timeout"; e.http_status = None; e.raw_error = "Connection timed out"
        r = fa.analyze(url="http://x.com", error_records=[e])
        assert r.failure_type == FailureType.REQUEST_FAILED

    def test_to_dict(self):
        fa = FailureAnalyzer()
        class FA: pass
        a1 = FA(); a1.success = False; a1.parser_name = "css"; a1.error = "no match"
        r = fa.analyze(url="http://x.com", parse_attempts=[a1])
        d = r.to_dict()
        assert d["failure_type"] == "selector_failed"
        assert d["recommend_ai_parser"] is True

    def test_severity_levels(self):
        assert Severity.FATAL.value == "fatal"
        assert Severity.LOW.value == "low"

    def test_failure_type_values(self):
        assert FailureType.SELECTOR_FAILED.value == "selector_failed"
        assert FailureType.AI_PARSER_FAILED.value == "ai_parser_failed"

    def test_html_structure_change_detected(self):
        fa = FailureAnalyzer()
        class SD: pass
        sd = SD(); sd.structure_changed = True; sd.change_score = 0.65; sd.failed_selectors = [".price"]
        r = fa.analyze(url="http://x.com", structure_diff_result=sd)
        assert r.failure_type == FailureType.HTML_STRUCTURE_CHANGED
        assert r.recommend_ai_parser

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
