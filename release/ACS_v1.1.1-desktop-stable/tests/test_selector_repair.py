"""Tests for acs.self_healing.selector_repair — candidate selector generation."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
from acs.self_healing.selector_repair import SelectorRepairer, FieldRepairResult, SelectorCandidate

TITLE_HTML = "<html><body><h1>iPhone 15 Pro Max</h1><meta property='og:title' content='iPhone 15 Pro Max - Apple Store'><div class='product-title'>Apple iPhone 15 Pro Max 256GB</div></body></html>"
PRICE_HTML = "<html><body><span class='product-price'>¥ 8,999</span><meta property='product:price:amount' content='8999.00'><div itemprop='price'>8999</div></body></html>"
BODY_HTML = "<html><body><article><p>This is a very long product description that should be detected as body content because it has more than fifty characters of text.</p></article></body></html>"
TIME_HTML = "<html><body><time datetime='2024-06-13T10:30:00'>2024年6月13日</time></body></html>"
EMPTY_HTML = ""

class TestSelectorRepairer:
    def test_repair_title_with_h1(self):
        rp = SelectorRepairer()
        result = rp.repair_field("title", "h1.old-title", TITLE_HTML)
        assert result.status == "pending_review"
        assert any("h1" in c.selector for c in result.candidate_selectors)

    def test_repair_title_with_og_meta(self):
        rp = SelectorRepairer()
        result = rp.repair_field("title", "h1.old", TITLE_HTML)
        selectors = [c.selector for c in result.candidate_selectors]
        assert any("og:title" in s for s in selectors)

    def test_repair_title_with_ai_hint_boosts_confidence(self):
        rp = SelectorRepairer()
        result = rp.repair_field("title", "h1.old", TITLE_HTML, ai_hint="iPhone 15 Pro Max")
        for c in result.candidate_selectors:
            if c.selector == "h1":
                assert c.confidence >= 0.90

    def test_repair_price(self):
        rp = SelectorRepairer()
        result = rp.repair_field("price", ".old-price", PRICE_HTML)
        assert len(result.candidate_selectors) >= 1
        assert any("price" in c.selector.lower() for c in result.candidate_selectors)

    def test_repair_body(self):
        rp = SelectorRepairer()
        result = rp.repair_field("body", ".old-content", BODY_HTML)
        assert len(result.candidate_selectors) >= 1
        assert any("article" in c.selector for c in result.candidate_selectors)

    def test_repair_time(self):
        rp = SelectorRepairer()
        result = rp.repair_field("published_time", ".old-date", TIME_HTML)
        assert len(result.candidate_selectors) >= 1
        assert any("time" in c.selector for c in result.candidate_selectors)

    def test_repair_empty_html(self):
        rp = SelectorRepairer()
        result = rp.repair_field("title", "h1", EMPTY_HTML)
        assert len(result.candidate_selectors) == 0
        assert result.status == "pending_review"

    def test_status_always_pending_review(self):
        rp = SelectorRepairer()
        result = rp.repair_field("title", "h1", TITLE_HTML)
        assert result.status == "pending_review"

    def test_field_repair_result_to_dict(self):
        rp = SelectorRepairer()
        result = rp.repair_field("title", "h1.old", TITLE_HTML)
        d = result.to_dict()
        assert d["status"] == "pending_review"
        assert d["field"] == "title"

    def test_repair_fields_batch(self):
        rp = SelectorRepairer()
        results = rp.repair_fields(
            [{"field": "title", "old_selector": "h1", "ai_hint": "iPhone"},
             {"field": "price", "old_selector": ".price", "ai_hint": "8999"}],
            TITLE_HTML + PRICE_HTML, url="http://x.com", site_id="test"
        )
        assert len(results) == 2
        assert results[0].field == "title"
        assert results[1].field == "price"

    def test_selector_candidate_to_dict(self):
        c = SelectorCandidate(selector="h1", confidence=0.85, evidence="found", match_count=1, sample_text="Test")
        d = c.to_dict()
        assert d["selector"] == "h1"
        assert d["confidence"] == 0.85

    def test_generic_candidate_with_ai_hint(self):
        rp = SelectorRepairer()
        candidates = rp._generic_candidates("<html>Some text with iPhone 15</html>", ".old", "iPhone 15")
        assert len(candidates) >= 1

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
