"""Tests for TopicCandidateRanker."""
import sys, os, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.discovery.topic_candidate_ranker import rank_topic_candidates

def test_blocked_always_last():
    cs = [
        {"url": "https://x.com/good", "title": "Good VOCs report", "snippet": "good", "source_domain": "epb.gov.cn", "compliance_status": "allowed", "content_type": "policy"},
        {"url": "https://x.com/bad", "title": "Bad", "snippet": "", "source_domain": "amazon.com", "compliance_status": "blocked"},
    ]
    ranked = rank_topic_candidates(cs, topic="VOCs", keywords=["VOCs"])
    assert ranked[-1]["compliance_status"] == "blocked"

def test_score_fields_added():
    cs = [
        {"url": "https://x.com/1", "title": "VOCs 治理案例", "snippet": "好的报告", "source_domain": "epb.gov.cn", "compliance_status": "allowed", "content_type": "case"},
    ]
    ranked = rank_topic_candidates(cs, topic="VOCs", keywords=["VOCs", "治理"])
    assert "_total_score" in ranked[0]
    assert ranked[0]["_total_score"] > 0
