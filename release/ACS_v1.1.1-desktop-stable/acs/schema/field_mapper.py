"""
Field mapper — maps ACS schema fields to AI-parseable format and back.

Provides deterministic transformations between:
  - ACS ParseResult → AI prompt context (what to tell the AI)
  - AI structured output → ACS ParseResult (merge AI results back)

This ensures the AI parser always works with the same field schema regardless
of which AI provider or model is used.

Usage:
    from acs.schema.field_mapper import FieldMapper
    mapper = FieldMapper()
    instruction = mapper.build_instruction()
    result = mapper.merge_ai_result(parse_result, ai_output)
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import json


# ── Field definitions for AI extraction ──────────────────────────

@dataclass
class AIField:
    """Definition of a single field the AI should extract."""
    name: str = ""              # ACS field name (e.g. "title")
    label_cn: str = ""          # Chinese label (e.g. "标题")
    description: str = ""       # What to extract
    required: bool = False
    expected_type: str = "string"  # string | number | list
    example: str = ""


# ── Standard extractable fields ──────────────────────────────────

STANDARD_AI_FIELDS: List[AIField] = [
    AIField("title", "标题", "页面主标题或商品名称", True, "string", "iPhone 15 Pro Max"),
    AIField("price", "价格", "商品价格，只提取数字和币种", False, "string", "¥8999"),
    AIField("published_time", "发布时间", "发布日期或更新时间", False, "string", "2024-06-13"),
    AIField("author", "作者/卖家", "作者、商家、发布者名称", False, "string", "Apple官方旗舰店"),
    AIField("body", "正文内容", "页面主要正文或商品描述", False, "string", "这是一款..."),
    AIField("images", "图片", "主要图片URL列表", False, "list", '["https://..."]'),
    AIField("price_currency", "币种", "价格币种：CNY/USD/JPY等", False, "string", "CNY"),
]


class FieldMapper:
    """Maps between ACS schema fields and AI extraction format.

    Args:
        fields: List of AIField definitions to extract
    """

    def __init__(self, fields: Optional[List[AIField]] = None):
        self.fields = fields or STANDARD_AI_FIELDS

    # ── Build AI instruction ─────────────────────────────────────

    def build_instruction(self, missing_fields: Optional[List[str]] = None) -> str:
        """Build extraction instructions for the AI parser.

        Args:
            missing_fields: Specific fields to focus on (None = all fields)

        Returns:
            Instruction text to include in the AI prompt
        """
        if missing_fields:
            target_fields = [f for f in self.fields if f.name in missing_fields]
        else:
            target_fields = list(self.fields)

        lines = ["从以下HTML页面中提取结构化数据。"]
        lines.append("")
        lines.append("需要提取的字段：")
        for i, f in enumerate(target_fields, 1):
            req = "【必填】" if f.required else "【选填】"
            lines.append(f"{i}. {f.label_cn}（{f.name}）{req}")
            lines.append(f"   说明：{f.description}")
            if f.example:
                lines.append(f"   示例：{f.example}")

        lines.append("")
        lines.append("请以JSON格式返回，每个字段包含 value/confidence/evidence：")
        lines.append(json.dumps(
            self._build_expected_schema(target_fields),
            ensure_ascii=False, indent=2
        ))

        lines.append("")
        lines.append("注意：")
        lines.append("- confidence 为 0.0（完全不确信）到 1.0（完全确信）")
        lines.append("- evidence 必须引用HTML中的具体文本或标签")
        lines.append("- 无法确定的字段 confidence 设为 0.0")
        lines.append("- 只返回JSON，不要添加解释文字")

        return "\n".join(lines)

    def build_prompt(self, html: str, missing_fields: Optional[List[str]] = None,
                     max_html_length: int = 8000) -> str:
        """Build a complete AI prompt with HTML content.

        Args:
            html: Page HTML content
            missing_fields: Specific fields to focus on
            max_html_length: Truncate HTML to this length for cost control

        Returns:
            Complete prompt string
        """
        html = (html or "")[:max_html_length]
        instruction = self.build_instruction(missing_fields)
        return f"{instruction}\n\n--- HTML 内容 ---\n{html}"

    def parse_ai_response(self, response_text: str) -> Dict[str, dict]:
        """Parse AI response into structured field data.

        Args:
            response_text: Raw AI response text

        Returns:
            Dict of field_name -> {value, confidence, evidence}
        """
        # Try to extract JSON from response
        json_text = self._extract_json(response_text)
        if json_text is None:
            return self._empty_result("AI response did not contain valid JSON")

        try:
            data = json.loads(json_text)
        except json.JSONDecodeError as e:
            return self._empty_result(f"JSON parse error: {e}")

        if not isinstance(data, dict):
            return self._empty_result("AI response is not a JSON object")

        # Normalize to standard field keys
        result = {}
        for field in self.fields:
            field_data = data.get(field.name, {})
            if isinstance(field_data, dict):
                result[field.name] = {
                    "value": field_data.get("value", ""),
                    "confidence": self._clamp_confidence(field_data.get("confidence", 0.0)),
                    "evidence": str(field_data.get("evidence", ""))[:500],
                    "extracted": True,
                }
            elif isinstance(field_data, (str, int, float)):
                result[field.name] = {
                    "value": str(field_data),
                    "confidence": 0.5,
                    "evidence": "AI returned bare value (no confidence provided)",
                    "extracted": True,
                }
            else:
                result[field.name] = {
                    "value": "",
                    "confidence": 0.0,
                    "evidence": "No data for this field",
                    "extracted": False,
                }

        return result

    # ── Merge into ParseResult ───────────────────────────────────

    def merge_ai_result(self, result, ai_fields: Dict[str, dict],
                        min_confidence: float = 0.5) -> Dict[str, Any]:
        """Merge AI-extracted fields into an existing ParseResult.

        Only fields with confidence >= min_confidence are merged.
        Existing non-empty fields are NOT overwritten unless AI confidence
        is higher than 0.8.

        Args:
            result: Existing ParseResult object
            ai_fields: Output from parse_ai_response()
            min_confidence: Minimum confidence to accept AI data

        Returns:
            Dict with merge details: {merged_fields, skipped_fields, low_confidence_fields}
        """
        merged = []
        skipped = []
        low_conf = []

        for field_name, ai_data in ai_fields.items():
            if not ai_data.get("extracted"):
                skipped.append(f"{field_name}: no data")
                continue

            confidence = ai_data.get("confidence", 0.0)
            value = ai_data.get("value", "")

            if not value:
                skipped.append(f"{field_name}: empty value")
                continue

            if confidence < min_confidence:
                low_conf.append({
                    "field": field_name,
                    "confidence": confidence,
                    "value_hint": str(value)[:100],
                })
                continue

            # Check existing value
            existing = getattr(result, field_name, "") if hasattr(result, field_name) else ""
            if existing and confidence < 0.8:
                skipped.append(f"{field_name}: existing value present, AI confidence < 0.8")
                continue

            # Merge
            old = getattr(result, field_name, "") if hasattr(result, field_name) else ""
            setattr(result, field_name, str(value)[:20000] if isinstance(value, str) else value)
            merged.append({
                "field": field_name,
                "old_value": str(old)[:100],
                "new_value": str(value)[:100],
                "confidence": confidence,
            })

        return {
            "merged_fields": merged,
            "skipped_fields": skipped,
            "low_confidence_fields": low_conf,
        }

    # ── Helpers ──────────────────────────────────────────────────

    def _build_expected_schema(self, fields: List[AIField]) -> dict:
        """Build the expected JSON schema for AI response."""
        schema = {}
        for f in fields:
            if f.expected_type == "list":
                schema[f.name] = {
                    "value": [],
                    "confidence": 0.0,
                    "evidence": "",
                }
            elif f.expected_type == "number":
                schema[f.name] = {
                    "value": 0,
                    "confidence": 0.0,
                    "evidence": "",
                }
            else:
                schema[f.name] = {
                    "value": "",
                    "confidence": 0.0,
                    "evidence": "",
                }
        return schema

    @staticmethod
    def _extract_json(text: str) -> Optional[str]:
        """Extract JSON from AI response (may have markdown wrapping)."""
        if not text:
            return None
        text = text.strip()

        # Direct JSON
        if text.startswith("{") and text.endswith("}"):
            return text

        # Markdown code block
        import re
        m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if m:
            return m.group(1)

        # Find first { to last }
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return text[start:end + 1]

        return None

    @staticmethod
    def _clamp_confidence(value: Any) -> float:
        try:
            v = float(value)
            return max(0.0, min(1.0, v))
        except (ValueError, TypeError):
            return 0.0

    def _empty_result(self, error: str) -> Dict[str, dict]:
        return {
            f.name: {"value": "", "confidence": 0.0, "evidence": error, "extracted": False}
            for f in self.fields
        }
