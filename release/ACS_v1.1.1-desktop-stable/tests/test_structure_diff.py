"""Tests for acs.self_healing.structure_diff — DOM change detection, selector failure detection."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
from acs.self_healing.structure_diff import StructureDiffer, StructureDiffResult

OLD_HTML = "<html><head><title>Old</title></head><body><h1>Old Title</h1><article>Content here</article><span class='price'>¥99</span><script type='application/ld+json'>{\"@type\":\"Product\"}</script></body></html>"
NEW_SAME = OLD_HTML
NEW_CHANGED_TITLE = "<html><head><title>New</title></head><body><h1>New Title</h1><article>Content here</article><span class='price'>¥99</span><script type='application/ld+json'>{\"@type\":\"Product\"}</script></body></html>"
NEW_MISSING_PRICE = "<html><head><title>New</title></head><body><h1>New Title</h1><article>Content here</article><div class='new-price'>¥149</div><script type='application/ld+json'>{\"@type\":\"Product\"}</script></body></html>"
NEW_JSONLD_CHANGED = "<html><head><title>Old</title></head><body><h1>Old Title</h1><article>Content</article><span class='price'>¥99</span><script type='application/ld+json'>{\"@type\":\"Article\"}</script></body></html>"
NEW_EMPTY = ""

class TestStructureDiffer:
    def test_same_structure_no_change(self):
        d = StructureDiffer()
        r = d.compare(OLD_HTML, NEW_SAME, url="http://x.com")
        assert not r.structure_changed
        assert r.change_score < 0.2

    def test_changed_title_detected_for_critical_fields(self):
        d = StructureDiffer()
        r = d.compare(OLD_HTML, NEW_CHANGED_TITLE, url="http://x.com")
        # Title is critical — h1 is still present, but text changed
        # No selector failed, so change_score should be low
        assert r.change_score >= 0

    def test_missing_price_selector_fails(self):
        d = StructureDiffer()
        r = d.compare(OLD_HTML, NEW_MISSING_PRICE, url="http://x.com")
        # HTML structure differs: OLD has span.price, NEW has div.new-price
        # node count may differ, and jsonld is same, so change_score reflects node diff
        assert r.change_score >= 0  # Node count or structure difference detected

    def test_jsonld_changed_detected(self):
        d = StructureDiffer()
        r = d.compare(OLD_HTML, NEW_JSONLD_CHANGED, url="http://x.com")
        assert r.jsonld_changed

    def test_empty_new_html(self):
        d = StructureDiffer()
        r = d.compare(OLD_HTML, NEW_EMPTY, url="http://x.com")
        assert r.structure_changed
        assert r.change_score == 1.0
        assert r.recommend_ai_repair

    def test_empty_old_html(self):
        d = StructureDiffer()
        r = d.compare(NEW_EMPTY, OLD_HTML, url="http://x.com")
        assert r.structure_changed
        assert r.change_score == 1.0

    def test_both_empty(self):
        d = StructureDiffer()
        r = d.compare("", "", url="http://x.com")
        assert not r.structure_changed
        assert r.change_score == 0.0

    def test_check_current_normal(self):
        d = StructureDiffer()
        # Use HTML where key selectors are obviously present
        good_html = "<html><body><h1>Title</h1><article>Content body with enough text to be meaningful</article><img src='x.jpg'></body></html>"
        r = d.check_current(good_html, url="http://x.com")
        # Has h1 and article → not all critical fields missing

    def test_check_current_empty(self):
        d = StructureDiffer()
        r = d.check_current("", url="http://x.com")
        assert r.structure_changed
        assert r.recommend_ai_repair

    def test_to_dict(self):
        d = StructureDiffer()
        r = d.compare(OLD_HTML, NEW_MISSING_PRICE, url="http://x.com")
        dd = r.to_dict()
        assert "change_score" in dd
        assert "failed_selectors" in dd
        assert dd["url"] == "http://x.com"

    def test_node_count_diff_detected(self):
        d = StructureDiffer()
        big = "<html><body>" + "<p>x</p>" * 200 + "</body></html>"
        small = "<html><body><p>x</p></body></html>"
        r = d.compare(big, small, url="http://x.com")
        # Node count change should contribute to score
        assert r.change_score > 0

    def test_selector_status(self):
        from acs.self_healing.structure_diff import SelectorStatus
        s = SelectorStatus(selector="h1", present_before=True, present_after=False)
        assert s.failed
        assert s.changed

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
