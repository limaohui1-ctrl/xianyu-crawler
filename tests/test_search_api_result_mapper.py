"""Tests: SearchApiResult → CandidateUrl mapping."""
import sys, os, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.discovery.topic_discovery_flow import _map_result_to_candidate
from acs.discovery.search_api_provider import SearchApiResult

def test_result_to_candidate():
    r = SearchApiResult(url="https://epb.gov.cn/doc", title="VOCs治理", snippet="案例", source_domain="epb.gov.cn")
    c = _map_result_to_candidate(r, "VOCs 治理")
    assert c["url"] == "https://epb.gov.cn/doc"
    assert c["discovery_method"] == "search_api"
    assert c["query"] == "VOCs 治理"

def test_content_type_detected():
    r = SearchApiResult(url="https://x.com/doc.pdf", title="报告", snippet="pdf 文档")
    c = _map_result_to_candidate(r, "test")
    assert c["content_type"] == "pdf"

def test_source_quality_set():
    r = SearchApiResult(url="https://epb.gov.cn/doc", title="T", source_domain="epb.gov.cn")
    c = _map_result_to_candidate(r, "q")
    assert c["source_quality_score"] > 0.5
