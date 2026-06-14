"""Tests: search API results → CandidateUrl mapping with real semantics."""
import sys, os, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.discovery.topic_discovery_flow import _map_result_to_candidate
from acs.discovery.search_api_provider import SearchApiResult

def test_real_result_mapped():
    r = SearchApiResult(
        url="https://epb.gov.cn/vocs-case",
        title="2025年工业园区VOCs治理典型案例汇编",
        snippet="生态环境部发布工业园区挥发性有机物治理典型案例",
        source_domain="epb.gov.cn",
        query="VOCs 治理 案例",
        rank=1,
    )
    c = _map_result_to_candidate(r, "VOCs 治理")
    assert c["url"] == "https://epb.gov.cn/vocs-case"
    assert c["discovery_method"] == "search_api"
    assert c["content_type"] == "policy"  # gov.cn domain
    assert c["source_quality_score"] > 0.9

def test_amazon_blocked_by_compliance():
    from acs.discovery.compliance_filter import ComplianceFilter
    from acs.discovery.candidate_url import CandidateUrl
    r = SearchApiResult(
        url="https://amazon.com/vocs-filter",
        title="VOCs Filter",
        snippet="Buy VOCs filter",
        source_domain="amazon.com",
    )
    c = _map_result_to_candidate(r, "VOCs")
    obj = CandidateUrl.from_dict(c)
    cf = ComplianceFilter()
    cf.evaluate(obj)
    assert obj.compliance_status == "blocked"
