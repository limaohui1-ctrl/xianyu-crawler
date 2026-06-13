"""Wizard plan application: use-case, market recommendations."""

from ui_registry import register

from universal_core import (
    AI_MODEL_USE_CASE_PRESETS,
    FieldRule,
    ai_preset_for,
    compact_text,
    normalize_url,
    recommend_template_market_items,
    template_market_items,

    SiteTemplate,

)
from core_urls import (
    normalize_url,
)



@register("apply_wizard_use_case")
def apply_wizard_use_case(self, plan):
    if not isinstance(plan, dict):
        return False
    use_case = plan.get("use_case") or {}
    use_case_key = use_case.get("key") or ""
    if not use_case_key:
        return False
    use_case_index = self.ai_use_case_combo.findData(use_case_key)
    if use_case_index < 0:
        return False
    self.ai_use_case_combo.setCurrentIndex(use_case_index)
    if (
        hasattr(self, "ai_auto_apply_use_case_checkbox")
        and not self.ai_auto_apply_use_case_checkbox.isChecked()
    ):
        self.append_ai_output(
            f"向导推荐模型用途：{use_case.get('name') or self.ai_use_case_combo.currentText()}；已保留当前手动模型。"
        )
        return True
    self.apply_ai_use_case_preset()
    self.append_ai_output(f"向导已自动选择模型用途：{use_case.get('name') or self.ai_use_case_combo.currentText()}")
    return True

@register("apply_market_recommendation_from_plan")
def apply_market_recommendation_from_plan(self, plan):
    if not hasattr(self, "template_market_table") or not isinstance(plan, dict):
        return False
    recommendations = recommend_template_market_items(plan=plan, limit=5)
    if not recommendations:
        self.template_market_recommend_label.setText("模板市场：未找到匹配模板")
        return False
    top = recommendations[0]
    template = top.get("template") or SiteTemplate(top.get("name", ""))
    use_case_key = top.get("recommended_use_case") or ""
    use_case_name = AI_MODEL_USE_CASE_PRESETS.get(use_case_key, {}).get("name", use_case_key)
    self.template_market_search_input.blockSignals(True)
    self.template_market_search_input.setText(template.name)
    self.template_market_search_input.blockSignals(False)
    all_index = self.template_market_category_combo.findText("全部分类")
    if all_index >= 0:
        self.template_market_category_combo.blockSignals(True)
        self.template_market_category_combo.setCurrentIndex(all_index)
        self.template_market_category_combo.blockSignals(False)
    self.refresh_template_market()
    for row, item in enumerate(getattr(self, "template_market_items", [])):
        candidate = item.get("template") or SiteTemplate(item.get("name", ""))
        if candidate.name == template.name:
            self.template_market_table.selectRow(row)
            break
    self.latest_market_recommendations = recommendations
    self.template_market_recommend_label.setText(
        f"模板市场推荐：{template.name}｜{top.get('category', '')}｜{use_case_name}｜评分 {top.get('score', 0)}"
    )
    self.append_ai_output(f"模板市场已自动推荐：{template.name}。{top.get('reason', '')}")
    return True
