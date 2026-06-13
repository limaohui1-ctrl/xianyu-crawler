"""Preview quality analysis and quality summary helpers."""

from ui_registry import register

import json

from universal_core import compact_text


@register("normalize_preview_value")
def normalize_preview_value(self, value):
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value).strip()

@register("analyze_preview_quality")
def analyze_preview_quality(self, rules, preview_values):
    issues = []
    seen_values = {}
    seen_selectors = {}
    for rule in rules:
        raw_value = preview_values.get(rule.name, "")
        value = self.normalize_preview_value(raw_value)
        status = "正常"
        problem = ""
        advice = "可以正式采集"
        score = 100
        if not value:
            status = "需处理"
            problem = "空值"
            advice = "检查 CSS 选择器是否匹配页面，或换一个字段"
            score = 20
        elif value in seen_values and len(value) > 0:
            status = "需确认"
            problem = f"与「{seen_values[value]}」值重复"
            advice = "可能两个字段抓到了同一块内容，建议修改其中一个选择器"
            score = 65
        elif rule.selector in seen_selectors:
            status = "需确认"
            problem = f"与「{seen_selectors[rule.selector]}」选择器重复"
            advice = "同一个选择器用于多个字段，确认是否符合预期"
            score = 70
        elif len(value) > 5000:
            status = "需确认"
            problem = "内容过长"
            advice = "可能抓到了整页正文，建议缩小选择器范围"
            score = 75
        seen_values.setdefault(value, rule.name)
        seen_selectors.setdefault(rule.selector, rule.name)
        issues.append(
            {
                "status": status,
                "score": score,
                "field": rule.name,
                "problem": problem or "无",
                "advice": advice,
                "selector": rule.selector,
            }
        )
    return issues

@register("quality_summary")
def quality_summary(self, issues):
    issues = issues or []
    if not issues:
        return {"score": 0, "need_fix": 0, "need_confirm": 0, "ok": 0, "summary": "字段质量评分：等待预采"}
    scores = [int(issue.get("score") or 0) for issue in issues]
    need_fix = sum(1 for issue in issues if issue.get("status") == "需处理")
    need_confirm = sum(1 for issue in issues if issue.get("status") == "需确认")
    ok_count = sum(1 for issue in issues if issue.get("status") == "正常")
    avg_score = round(sum(scores) / max(1, len(scores)))
    if need_fix:
        level = "需要修复"
    elif need_confirm:
        level = "建议确认"
    else:
        level = "可以采集"
    return {
        "score": avg_score,
        "need_fix": need_fix,
        "need_confirm": need_confirm,
        "ok": ok_count,
        "summary": f"字段质量评分：{avg_score}/100，{level}；正常 {ok_count}，需确认 {need_confirm}，需处理 {need_fix}",
    }
