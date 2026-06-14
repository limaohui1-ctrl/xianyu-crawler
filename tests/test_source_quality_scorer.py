"""Tests for SourceQualityScorer."""
import sys, os, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.discovery.source_quality_scorer import score_source_quality

def test_gov_high():
    assert score_source_quality("epb.gov.cn") > 0.8
    assert score_source_quality("www.mee.gov.cn") > 0.8

def test_edu_high():
    assert score_source_quality("tsinghua.edu.cn") > 0.8

def test_org_high():
    assert score_source_quality("chinaenvironment.org") > 0.7

def test_commercial_low():
    assert score_source_quality("amazon.com") < 0.3

def test_blog_low():
    assert score_source_quality("someblog.blogspot.com") < 0.5
