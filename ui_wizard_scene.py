"""Wizard scene prompt and preview helpers."""

from ui_registry import register

from PyQt6.QtWidgets import QMessageBox

from universal_core import (
    FieldRule,
    SiteTemplate,
    UniversalExtractor,
    scene_template_presets,
)


@register("default_prompt_for_scene")
def default_prompt_for_scene(self, preset):
    prompt_map = {
        "ecommerce": "抓取商品标题、价格、库存/规格、详情、图片和详情页链接",
        "article": "抓取文章标题、发布时间、作者/来源、正文和相关链接",
        "jobs": "抓取职位名称、薪资、公司、地点、岗位描述和详情链接",
        "company": "抓取公司名称、联系人、电话/邮箱、简介、官网和详情链接",
        "forum": "抓取帖子标题、作者、发布时间、正文、评论/互动信息和图片",
        "gallery": "抓取标题、图片地址、图片说明和详情页链接",
        "real_estate": "抓取房源标题、价格、面积/户型、位置、经纪人、详情和图片",
        "local_service": "抓取服务名称、价格/费用、联系人、电话/邮箱、服务介绍和地址",
    }
    return prompt_map.get(preset.template_type, "抓取当前页面的主要表格字段、图片、链接和正文")

@register("run_wizard_preview")
def run_wizard_preview(self, plan, html):
    if not isinstance(plan, dict) or not html:
        return False
    url = plan.get("url") or self.first_target_url()
    template_data = plan.get("template", {}) or {}
    rules = [
        FieldRule.from_dict(item)
        for item in template_data.get("field_rules", []) or []
        if isinstance(item, dict) and str(item.get("name", "")).strip()
    ]
    if not url or not rules:
        return False
    try:
        template = SiteTemplate(
            template_data.get("name") or "向导预采模板",
            field_rules=rules,
            next_page_selector=template_data.get("next_page_selector", ""),
        )
        record = UniversalExtractor(template).extract(html, url)
    except Exception as exc:
        self.append_ai_output(f"向导预采评分失败：{exc}")
        return False
    self.latest_preview_url = url
    self.latest_preview_html = html
    self.latest_preview_rules = rules
    self.show_preview_record(record, rules)
    self.append_ai_output(f"向导已自动预采 1 页并完成字段质量评分：{url}")
    return True
