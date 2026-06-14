"""Tests for acs.schema.field_mapper — field definitions, prompt building, AI response parsing."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest, json
from acs.schema.field_mapper import FieldMapper, AIField, STANDARD_AI_FIELDS

VALID_AI_RESPONSE = json.dumps({"title": {"value": "Test Product", "confidence": 0.95, "evidence": "h1 tag"}, "price": {"value": "¥99", "confidence": 0.90, "evidence": "price div"}}, ensure_ascii=False)
MD_WRAPPED_RESPONSE = "```json\n" + VALID_AI_RESPONSE + "\n```"
BARE_VALUE_RESPONSE = json.dumps({"title": "Just a string", "price": 99}, ensure_ascii=False)
NOT_JSON_RESPONSE = "I found a product called Test Product"

class TestFieldMapper:
    def test_fields_exist(self): assert len(STANDARD_AI_FIELDS) >= 6

    def test_build_instruction(self):
        fm = FieldMapper()
        instr = fm.build_instruction()
        assert "标题" in instr
        assert "price" in instr
        assert "json" in instr.lower()

    def test_build_instruction_missing_fields(self):
        fm = FieldMapper()
        instr = fm.build_instruction(missing_fields=["title", "price"])
        assert "title" in instr
        assert "price" in instr
        # title is required so 【必填】 should appear
        assert "必填" in instr

    def test_build_prompt(self):
        fm = FieldMapper()
        prompt = fm.build_prompt("<html><h1>Test</h1></html>")
        assert "Test" in prompt
        assert "HTML" in prompt

    def test_build_prompt_truncates(self):
        fm = FieldMapper()
        prompt = fm.build_prompt("x" * 20000, max_html_length=100)
        assert len(prompt.split("--- HTML")[-1]) < 200

    def test_parse_ai_response_valid_json(self):
        fm = FieldMapper()
        fields = fm.parse_ai_response(VALID_AI_RESPONSE)
        assert fields["title"]["value"] == "Test Product"
        assert fields["title"]["confidence"] == 0.95
        assert fields["title"]["extracted"] is True
        assert fields["price"]["value"] == "¥99"

    def test_parse_ai_response_markdown_wrapped(self):
        fm = FieldMapper()
        fields = fm.parse_ai_response(MD_WRAPPED_RESPONSE)
        assert fields["title"]["value"] == "Test Product"

    def test_parse_ai_response_bare_values(self):
        fm = FieldMapper()
        fields = fm.parse_ai_response(BARE_VALUE_RESPONSE)
        assert fields["title"]["value"] == "Just a string"
        assert fields["title"]["confidence"] == 0.5  # Default for bare values

    def test_parse_ai_response_not_json(self):
        fm = FieldMapper()
        fields = fm.parse_ai_response(NOT_JSON_RESPONSE)
        assert all(not f["extracted"] for f in fields.values())

    def test_parse_ai_response_empty(self):
        fm = FieldMapper()
        fields = fm.parse_ai_response("")
        assert all(not f["extracted"] for f in fields.values())

    def test_merge_ai_result(self):
        from acs.core.result_model import ParseResult
        r = ParseResult(url="http://x.com", title="")
        fm = FieldMapper()
        fields = fm.parse_ai_response(VALID_AI_RESPONSE)
        info = fm.merge_ai_result(r, fields, min_confidence=0.5)
        assert r.title == "Test Product"
        assert any("title" in m["field"] for m in info["merged_fields"])

    def test_merge_respects_min_confidence(self):
        from acs.core.result_model import ParseResult
        r = ParseResult(url="http://x.com", title="")
        fm = FieldMapper()
        fields = fm.parse_ai_response(VALID_AI_RESPONSE)
        info = fm.merge_ai_result(r, fields, min_confidence=0.99)
        assert r.title == ""  # 0.95 < 0.99, skipped
        assert len(info["low_confidence_fields"]) >= 1

    def test_clamp_confidence(self):
        assert FieldMapper._clamp_confidence(1.5) == 1.0
        assert FieldMapper._clamp_confidence(-0.5) == 0.0
        assert FieldMapper._clamp_confidence(0.73) == 0.73
        assert FieldMapper._clamp_confidence("bad") == 0.0

    def test_extract_json_direct(self):
        assert FieldMapper._extract_json('{"a":1}') == '{"a":1}'
        # With whitespace, strip() makes it start with { and end with } → should match
        j = FieldMapper._extract_json('  {"a": 1}  ')
        assert j is not None
        assert '"a"' in j

    def test_extract_json_in_text(self):
        j = FieldMapper._extract_json("Here is the result: {\"key\":\"value\"}")
        assert j is not None
        assert "key" in j

    def test_ai_field_dataclass(self):
        f = AIField(name="test", label_cn="测试", description="desc", required=True)
        assert f.name == "test"
        assert f.required is True

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
