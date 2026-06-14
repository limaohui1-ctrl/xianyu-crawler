"""Tests for relevance_ranker."""
import sys, os, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.discovery.relevance_ranker import RelevanceRanker
from acs.discovery.candidate_url import CandidateUrl


def test_rank_empty():
    ranker = RelevanceRanker()
    result = ranker.rank([], "test", ["test"])
    assert result == []


def test_rank_scores_candidates():
    ranker = RelevanceRanker()
    candidates = [
        CandidateUrl(url="https://x.com/1", title="VOCs治理案例", snippet="活性炭吸附",
                     source_domain="epb.gov.cn", compliance_status="allowed"),
        CandidateUrl(url="https://x.com/2", title="不相关内容", snippet="nothing",
                     source_domain="example.com", compliance_status="needs_review"),
    ]
    ranked = ranker.rank(candidates, "VOCs治理", ["VOCs", "活性炭"])
    assert ranked[0].estimated_relevance > ranked[1].estimated_relevance


def test_rank_blocked_pushed_bottom():
    ranker = RelevanceRanker()
    candidates = [
        CandidateUrl(url="https://x.com/1", title="普通页面", snippet="test",
                     source_domain="epb.gov.cn", compliance_status="allowed"),
        CandidateUrl(url="https://x.com/2", title="被阻止页面", snippet="test",
                     source_domain="amazon.com", compliance_status="blocked"),
    ]
    ranked = ranker.rank(candidates, "test", ["test"])
    assert ranked[0].compliance_status != "blocked"
    assert ranked[-1].compliance_status == "blocked"


def test_rank_gov_domain_bonus():
    ranker = RelevanceRanker()
    c = CandidateUrl(url="https://x.gov.cn/1", title="治理 test", snippet="test",
                     source_domain="x.gov.cn", compliance_status="allowed")
    ranked = ranker.rank([c], "治理", ["治理"])
    assert ranked[0].estimated_relevance > 0


def test_rank_score_in_range():
    ranker = RelevanceRanker()
    candidates = [
        CandidateUrl(url=f"https://x.com/{i}", title=f"治理案例 {i}",
                     snippet="活性炭 废气治理", source_domain="epb.gov.cn",
                     compliance_status="allowed")
        for i in range(5)
    ]
    ranked = ranker.rank(candidates, "治理", ["治理", "活性炭"])
    for c in ranked:
        assert 0 <= c.estimated_relevance <= 1.0


def test_rank_stable():
    ranker = RelevanceRanker()
    c1 = CandidateUrl(url="https://x.com/a", title="治理", snippet="治理",
                      source_domain="epb.gov.cn", compliance_status="allowed")
    c2 = CandidateUrl(url="https://x.com/b", title="治理", snippet="治理",
                      source_domain="epb.gov.cn", compliance_status="allowed")
    r1 = ranker.rank([c1, c2], "治理", ["治理"])
    r2 = ranker.rank([c1, c2], "治理", ["治理"])
    assert r1[0].url == r2[0].url
