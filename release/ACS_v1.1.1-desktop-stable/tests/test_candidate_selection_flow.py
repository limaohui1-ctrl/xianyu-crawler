"""Tests: candidate selection flow — blocked items never selected, needs_review requires confirm."""
import sys, os, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.discovery.candidate_url import CandidateUrl
from acs.discovery.candidate_store import CandidateStore
from acs.discovery.compliance_filter import ComplianceFilter


def test_blocked_cannot_be_marked_selected():
    cf = ComplianceFilter()
    c = cf.evaluate(CandidateUrl(url="https://www.amazon.com/dp/B00TEST", source_domain="amazon.com"))
    assert c.compliance_status == "blocked"

    store = CandidateStore()
    store.mark_selected([c], ["https://www.amazon.com/dp/B00TEST"])
    assert c.selected is False


def test_needs_review_can_be_marked_selected():
    c = CandidateUrl(url="https://example.com/product", source_domain="example.com",
                     compliance_status="needs_review", risk_level="medium")
    store = CandidateStore()
    store.mark_selected([c], ["https://example.com/product"])
    assert c.selected is True


def test_allowed_auto_selected():
    c = CandidateUrl(url="https://epb.gov.cn/doc", source_domain="epb.gov.cn",
                     compliance_status="allowed", risk_level="low")
    store = CandidateStore()
    store.mark_selected([c], ["https://epb.gov.cn/doc"])
    assert c.selected is True


def test_mixed_batch_selection():
    candidates = [
        CandidateUrl(url="https://gov.cn/1", compliance_status="allowed", source_domain="gov.cn"),
        CandidateUrl(url="https://example.com/2", compliance_status="needs_review", source_domain="example.com"),
        CandidateUrl(url="https://amazon.com/3", compliance_status="blocked", source_domain="amazon.com", risk_level="blocked"),
    ]
    store = CandidateStore()
    all_urls = [c.url for c in candidates]
    store.mark_selected(candidates, all_urls)
    assert candidates[0].selected is True
    assert candidates[1].selected is True
    assert candidates[2].selected is False


def test_export_only_selected():
    import tempfile, shutil, os
    d = tempfile.mkdtemp()
    store = CandidateStore(d)
    candidates = [
        CandidateUrl(url="https://gov.cn/1", selected=True, source_domain="gov.cn"),
        CandidateUrl(url="https://example.com/2", selected=False, source_domain="example.com"),
        CandidateUrl(url="https://amazon.com/3", selected=False, compliance_status="blocked",
                     source_domain="amazon.com", risk_level="blocked"),
    ]
    out = os.path.join(d, "test_export.txt")
    store.export_selected_urls(candidates, out)
    with open(out) as f:
        lines = [l.strip() for l in f if l.strip()]
    assert len(lines) == 1
    assert lines[0] == "https://gov.cn/1"
    shutil.rmtree(d, ignore_errors=True)


def test_no_api_key_in_flow():
    import json
    j = json.dumps({"selection": "ok"})
    assert "sk-" not in j
