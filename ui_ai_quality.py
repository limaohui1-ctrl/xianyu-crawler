"""AI result-quality analysis and field-repair helpers."""

from ui_registry import register

import json

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMessageBox, QTableWidgetItem

from universal_core import (
    AI_PROVIDER_PRESETS,
    FieldRule,
    SiteTemplate,
    UniversalExtractor,
    append_ai_repair_history,
    normalize_url,
    record_recoverable_error,
)
from core_urls import (
    normalize_url,
)



@register("fill_quality_table")
def fill_quality_table(self, issues):
    self.ai_quality_table.setRowCount(0)
    summary = self.quality_summary(issues)
    if hasattr(self, "ai_quality_score_label"):
        self.ai_quality_score_label.setText(summary.get("summary", "字段质量评分：等待预采"))
    for issue in issues:
        row = self.ai_quality_table.rowCount()
        self.ai_quality_table.insertRow(row)
        values = [
            issue.get("status", ""),
            issue.get("score", ""),
            issue.get("field", ""),
            issue.get("problem", ""),
            issue.get("advice", ""),
            issue.get("selector", ""),
        ]
        for column, value in enumerate(values):
            item = QTableWidgetItem(str(value))
            item.setToolTip(str(value))
            if column == 0 and value == "需处理":
                item.setBackground(Qt.GlobalColor.red)
            elif column == 0 and value == "需确认":
                item.setBackground(Qt.GlobalColor.yellow)
            self.ai_quality_table.setItem(row, column, item)

@register("result_quality_fields")
def result_quality_fields(self):
    base_fields = [
        ("标题", "title"),
        ("价格", "price"),
        ("时间", "published_time"),
        ("作者", "author"),
        ("正文", "body"),
        ("图片", "images"),
        ("链接", "links"),
        ("表格", "tables"),
        ("错误", "error"),
    ]
    custom_names = []
    for rule in self.collect_field_rules_from_table():
        if rule.name not in [name for name, _key in base_fields] and rule.name not in custom_names:
            custom_names.append(rule.name)
    return base_fields + [(name, name) for name in custom_names]

@register("record_quality_value")
def record_quality_value(self, record, key):
    if key in record:
        return record.get(key, "")
    body = record.get("body", "")
    marker = "自定义字段："
    if marker in body:
        try:
            custom_values = json.loads(body.split(marker, 1)[1].strip())
            return custom_values.get(key, "")
        except Exception as exc:
            record_recoverable_error(
                "解析结果自定义字段失败，已留空该字段",
                exc,
                details={"field": key},
            )
            return ""
    return ""

@register("analyze_result_quality")
def analyze_result_quality(self, records=None):
    records = list(records if records is not None else self.records)
    if not records:
        return []
    total = len(records)
    issues = []
    for field_name, key in self.result_quality_fields():
        values = [self.normalize_preview_value(self.record_quality_value(record, key)) for record in records]
        empty_count = sum(1 for value in values if not value or value in {"[]", "{}"})
        non_empty = [value for value in values if value and value not in {"[]", "{}"}]
        duplicate_count = max(0, len(non_empty) - len(set(non_empty)))
        long_count = sum(1 for value in non_empty if len(value) > 5000)
        empty_rate = empty_count / max(1, total)
        duplicate_rate = duplicate_count / max(1, len(non_empty))
        score = 100
        problems = []
        advice = "可以继续使用"
        status = "正常"
        if key == "error" and non_empty:
            status = "需处理"
            score = 25
            problems.append(f"存在 {len(non_empty)} 条错误")
            advice = "查看错误列，必要时放慢采集或切换真实浏览器模式"
        elif empty_rate >= 0.8:
            status = "需处理"
            score = 25
            problems.append(f"空值率 {round(empty_rate * 100)}%")
            advice = "字段可能没有抓到，建议点 AI 修复问题列或调整选择器"
        elif empty_rate >= 0.4:
            status = "需确认"
            score = 60
            problems.append(f"空值率 {round(empty_rate * 100)}%")
            advice = "部分页面可能缺字段，建议抽查结果或增加子页面抓取"
        if key != "error" and duplicate_rate >= 0.6 and len(non_empty) >= 3:
            status = "需确认" if status == "正常" else status
            score = min(score, 65)
            problems.append(f"重复率 {round(duplicate_rate * 100)}%")
            advice = "可能抓到了同一块内容，建议检查选择器是否过宽"
        if long_count:
            status = "需确认" if status == "正常" else status
            score = min(score, 70)
            problems.append(f"{long_count} 条内容过长")
            advice = "可能抓到整页正文，建议缩小字段范围"
        issues.append(
            {
                "status": status,
                "score": score,
                "field": field_name,
                "empty": f"{empty_count}/{total}",
                "duplicate": f"{duplicate_count}/{max(1, len(non_empty))}",
                "problem": "；".join(problems) if problems else "无",
                "advice": advice,
            }
        )
    return issues

@register("result_quality_summary")
def result_quality_summary(self, issues):
    issues = issues or []
    if not issues:
        return "采集结果质量：等待结果"
    scores = [int(issue.get("score") or 0) for issue in issues]
    need_fix = sum(1 for issue in issues if issue.get("status") == "需处理")
    need_confirm = sum(1 for issue in issues if issue.get("status") == "需确认")
    ok_count = sum(1 for issue in issues if issue.get("status") == "正常")
    avg_score = round(sum(scores) / max(1, len(scores)))
    if need_fix:
        level = "需要修复"
    elif need_confirm:
        level = "建议抽查"
    else:
        level = "质量正常"
    return f"采集结果质量：{avg_score}/100，{level}；正常 {ok_count}，需确认 {need_confirm}，需处理 {need_fix}"

@register("fill_result_quality_table")
def fill_result_quality_table(self, issues=None):
    if not hasattr(self, "result_quality_table"):
        return
    issues = self.analyze_result_quality() if issues is None else issues
    self.result_quality_table.setRowCount(0)
    if hasattr(self, "result_quality_score_label"):
        self.result_quality_score_label.setText(self.result_quality_summary(issues))
    for issue in issues:
        row = self.result_quality_table.rowCount()
        self.result_quality_table.insertRow(row)
        values = [
            issue.get("status", ""),
            issue.get("score", ""),
            issue.get("field", ""),
            issue.get("empty", ""),
            issue.get("duplicate", ""),
            issue.get("problem", ""),
            issue.get("advice", ""),
        ]
        for column, value in enumerate(values):
            item = QTableWidgetItem(str(value))
            item.setToolTip(str(value))
            if column == 0 and value == "需处理":
                item.setBackground(Qt.GlobalColor.red)
            elif column == 0 and value == "需确认":
                item.setBackground(Qt.GlobalColor.yellow)
            self.result_quality_table.setItem(row, column, item)

@register("repair_quality_report_summary")
def repair_quality_report_summary(self, rows):
    rows = rows or []
    if not rows:
        return "AI 修复验证：等待修复"
    improved = sum(1 for row in rows if row.get("result") == "改善")
    worse = sum(1 for row in rows if row.get("result") == "变差")
    unchanged = len(rows) - improved - worse
    before_scores = [int(row.get("before_score") or 0) for row in rows]
    after_scores = [int(row.get("after_score") or 0) for row in rows]
    before_avg = round(sum(before_scores) / max(1, len(before_scores)))
    after_avg = round(sum(after_scores) / max(1, len(after_scores)))
    delta = after_avg - before_avg
    level = "已改善" if improved and not worse else ("需继续调整" if worse else "变化不明显")
    sample_count = max(int(row.get("sample_count") or 0) for row in rows)
    sample_text = f"；样本 {sample_count} 条" if sample_count else ""
    return f"AI 修复验证：{before_avg} -> {after_avg}，{level}；改善 {improved}，持平 {unchanged}，变差 {worse}，总变化 {delta:+d}{sample_text}"

@register("build_repair_quality_report")
def build_repair_quality_report(self, before_issues, after_issues):
    before_by_field = {item.get("field", ""): item for item in before_issues or [] if item.get("field")}
    after_by_field = {item.get("field", ""): item for item in after_issues or [] if item.get("field")}
    fields = []
    for field in list(before_by_field.keys()) + list(after_by_field.keys()):
        if field and field not in fields:
            fields.append(field)
    rows = []
    status_rank = {"正常": 0, "需确认": 1, "需处理": 2}
    for field in fields:
        before = before_by_field.get(field, {})
        after = after_by_field.get(field, {})
        before_score = int(before.get("score") or 0)
        after_score = int(after.get("score") or 0)
        before_status = before.get("status", "未检测")
        after_status = after.get("status", "未检测")
        before_rank = status_rank.get(before_status, 3)
        after_rank = status_rank.get(after_status, 3)
        delta = after_score - before_score
        if after_rank < before_rank or delta >= 10:
            result = "改善"
        elif after_rank > before_rank or delta <= -10:
            result = "变差"
        else:
            result = "持平"
        before_problem = before.get("problem", "无")
        after_problem = after.get("problem", "无")
        if result == "改善":
            advice = "可以保留当前修复字段"
        elif result == "变差":
            advice = "建议撤回或继续让 AI 缩小选择器"
        else:
            advice = after.get("advice") or before.get("advice") or "建议抽查样本"
        rows.append(
            {
                "field": field,
                "sample_count": after.get("sample_count") or before.get("sample_count") or "",
                "before_score": before_score,
                "after_score": after_score,
                "score_delta": delta,
                "before_status": before_status,
                "after_status": after_status,
                "before_problem": before_problem,
                "after_problem": after_problem,
                "advice": advice,
                "result": result,
            }
        )
    return rows

@register("fill_repair_quality_report_table")
def fill_repair_quality_report_table(self, rows=None):
    if not hasattr(self, "repair_quality_report_table"):
        return
    rows = [] if rows is None else list(rows)
    self.repair_quality_report_rows = rows
    self.repair_quality_report_table.setRowCount(0)
    if hasattr(self, "repair_quality_report_label"):
        self.repair_quality_report_label.setText(self.repair_quality_report_summary(rows))
    for report in rows:
        row = self.repair_quality_report_table.rowCount()
        self.repair_quality_report_table.insertRow(row)
        delta = int(report.get("score_delta") or 0)
        values = [
            report.get("field", ""),
            report.get("sample_count", ""),
            f"{report.get('before_score', 0)}/{report.get('before_status', '')}",
            f"{report.get('after_score', 0)}/{report.get('after_status', '')}",
            f"{delta:+d}",
            f"{report.get('before_status', '')} -> {report.get('after_status', '')}",
            f"{report.get('before_problem', '')} -> {report.get('after_problem', '')}",
            report.get("advice", ""),
            report.get("result", ""),
        ]
        for column, value in enumerate(values):
            item = QTableWidgetItem(str(value))
            item.setToolTip(str(value))
            if column == 8 and value == "改善":
                item.setBackground(Qt.GlobalColor.green)
            elif column == 8 and value == "变差":
                item.setBackground(Qt.GlobalColor.red)
            elif column == 8 and value == "持平":
                item.setBackground(Qt.GlobalColor.yellow)
            self.repair_quality_report_table.setItem(row, column, item)

@register("update_repair_quality_report")
def update_repair_quality_report(self, before_issues, after_issues):
    rows = self.build_repair_quality_report(before_issues, after_issues)
    self.fill_repair_quality_report_table(rows)
    if rows:
        self.append_ai_output(self.repair_quality_report_summary(rows))
        self.save_ai_repair_history(rows)
        self.prepare_secondary_repair_prompt(rows)
    return rows

@register("ai_repair_history_entry")
def ai_repair_history_entry(self, rows):
    rows = list(rows or [])
    improved = sum(1 for row in rows if row.get("result") == "改善")
    worse = sum(1 for row in rows if row.get("result") == "变差")
    unchanged = len(rows) - improved - worse
    deltas = [int(row.get("score_delta") or 0) for row in rows]
    sample_count = max([int(row.get("sample_count") or 0) for row in rows] or [0])
    failed_fields = [row.get("field", "") for row in rows if row.get("result") in ("持平", "变差")]
    provider = self.ai_provider_combo.currentData() if hasattr(self, "ai_provider_combo") else self.ai_settings.get("provider", "")
    provider_name = (AI_PROVIDER_PRESETS.get(provider, {}) or {}).get("name") or self.ai_settings.get("provider_name", provider)
    model = self.current_ai_model_text() if hasattr(self, "ai_model_combo") else self.ai_settings.get("model", "")
    return {
        "provider": provider,
        "provider_name": provider_name,
        "model": model,
        "sample_count": sample_count,
        "field_count": len(rows),
        "improved_count": improved,
        "unchanged_count": unchanged,
        "worse_count": worse,
        "avg_delta": round(sum(deltas) / max(1, len(deltas)), 1),
        "failed_fields": failed_fields,
        "field_rules": [rule.to_dict() for rule in self.collect_field_rules_from_table()],
        "report_rows": rows,
    }

@register("save_ai_repair_history")
def save_ai_repair_history(self, rows):
    if not rows:
        return None
    entry = append_ai_repair_history(self.ai_repair_history_entry(rows))
    self.refresh_ai_repair_history()
    return entry

@register("secondary_repair_issues_from_report")
def secondary_repair_issues_from_report(self, rows):
    rules_by_name = {rule.name: rule for rule in self.collect_field_rules_from_table()}
    issues = []
    for row in rows or []:
        if row.get("result") == "改善":
            continue
        field = row.get("field", "")
        if not field:
            continue
        rule = rules_by_name.get(field)
        issues.append(
            {
                "status": "需处理" if row.get("result") == "变差" else "需确认",
                "score": row.get("after_score", ""),
                "field": field,
                "problem": f"修复后仍未稳定：{row.get('after_problem', '')}",
                "advice": row.get("advice", "继续缩小选择器或换更准确字段来源"),
                "selector": rule.selector if rule else "",
                "sample_count": row.get("sample_count", ""),
                "score_delta": row.get("score_delta", ""),
                "repair_result": row.get("result", ""),
            }
        )
    return issues

@register("secondary_repair_prompt_text")
def secondary_repair_prompt_text(self, issues):
    if not issues:
        return ""
    lines = [
        "请继续修复上一轮没有变好的字段，优先让多样本验证变为“改善”：",
    ]
    for issue in issues:
        selector = issue.get("selector") or "未填写"
        sample_count = issue.get("sample_count") or "未知"
        delta = issue.get("score_delta")
        lines.append(
            f"- {issue.get('field')}：{issue.get('repair_result')}，{issue.get('problem')}；"
            f"当前选择器：{selector}；样本数：{sample_count}；分数变化：{delta}"
        )
    lines.append("要求：不要删除已经改善的字段；只调整以上失败字段；返回完整 fields 数组。")
    return "\n".join(lines)

@register("prepare_secondary_repair_prompt")
def prepare_secondary_repair_prompt(self, report_rows):
    issues = self.secondary_repair_issues_from_report(report_rows)
    self.secondary_repair_issues = issues
    if not issues:
        return []
    prompt = self.secondary_repair_prompt_text(issues)
    if prompt:
        self.ai_prompt_input.setPlainText(prompt)
    self.append_ai_output(f"已准备二次 AI 修复提示：{len(issues)} 个字段仍需继续修。")
    return issues

@register("repair_sample_sources")
def repair_sample_sources(self, limit=3):
    sources = []
    seen = set()
    for record in list(self.records or []):
        url = normalize_url(record.get("url", ""))
        if not url or url in seen:
            continue
        seen.add(url)
        sources.append({"url": url, "html": ""})
        if len(sources) >= limit:
            return sources
    if self.latest_preview_url and self.latest_preview_html:
        sources.append({"url": self.latest_preview_url, "html": self.latest_preview_html})
    return sources[:limit]

@register("verify_repaired_fields_on_samples")
def verify_repaired_fields_on_samples(self, rules, limit=3):
    sources = self.repair_sample_sources(limit)
    if not sources:
        return []
    template = SiteTemplate("AI 修复多样本验证模板", field_rules=rules)
    extractor = UniversalExtractor(template)
    verified_records = []
    for source in sources:
        url = normalize_url(source.get("url", ""))
        html = source.get("html", "")
        if not url:
            continue
        if not html:
            if url == self.latest_preview_url and self.latest_preview_html:
                html = self.latest_preview_html
            else:
                try:
                    html = self.fetch_snapshot_html(url)
                except Exception as exc:
                    verified_records.append({"url": url, "error": f"重采样失败：{exc}"})
                    continue
        try:
            verified_records.append(extractor.extract(html, url))
        except Exception as exc:
            verified_records.append({"url": url, "error": f"重采样抽取失败：{exc}"})
    return verified_records

@register("analyze_repaired_sample_quality")
def analyze_repaired_sample_quality(self, records, fields):
    issues = self.analyze_result_quality(records)
    wanted = set(fields or [])
    result = []
    sample_count = len(records or [])
    for issue in issues:
        if wanted and issue.get("field") not in wanted:
            continue
        item = dict(issue)
        item["sample_count"] = sample_count
        result.append(item)
    return result

@register("result_quality_issues_for_repair")
def result_quality_issues_for_repair(self, issues=None):
    issues = issues if issues is not None else self.analyze_result_quality()
    repair_issues = []
    rules_by_name = {rule.name: rule for rule in self.collect_field_rules_from_table()}
    for issue in issues or []:
        if issue.get("status") not in ("需处理", "需确认"):
            continue
        field = issue.get("field", "")
        if field == "错误":
            continue
        rule = rules_by_name.get(field)
        repair_issues.append(
            {
                "status": issue.get("status", ""),
                "score": issue.get("score", ""),
                "field": field,
                "problem": issue.get("problem", ""),
                "advice": issue.get("advice", ""),
                "selector": rule.selector if rule else "",
                "empty": issue.get("empty", ""),
                "duplicate": issue.get("duplicate", ""),
            }
        )
    return repair_issues

@register("ai_repair_from_result_quality")
def ai_repair_from_result_quality(self):
    issues = self.result_quality_issues_for_repair()
    if not issues:
        QMessageBox.information(self, "提示", "当前采集结果质量没有可自动修复的字段问题。")
        return
    rules = self.collect_field_rules_from_table()
    if not rules:
        QMessageBox.information(self, "提示", "请先在模板库配置字段，或先让 AI 建议列。")
        return
    url = self.latest_preview_url or self.first_target_url()
    if not url and self.records:
        url = self.records[0].get("url", "")
    html = self.latest_preview_html
    if not url:
        QMessageBox.information(self, "提示", "没有可用于修复的样本网址。")
        return
    if not html:
        try:
            html = self.fetch_snapshot_html(url)
        except Exception as exc:
            QMessageBox.warning(self, "读取网页失败", str(exc))
            return
    self.latest_quality_issues = issues
    self.fill_quality_table(issues)
    self.latest_preview_url = url
    self.latest_preview_html = html
    self.latest_preview_rules = rules
    self.repair_quality_before_issues = [dict(issue) for issue in issues]
    self.fill_repair_quality_report_table([])
    self.auto_apply_repair_after_ai = True
    self.append_ai_output(f"已把采集结果质量问题转为 AI 修复任务：{len(issues)} 个字段。")
    self.run_ai_worker(
        "repair_fields",
        {
            "url": url,
            "html": html,
            "field_rules": [rule.to_dict() for rule in rules],
            "quality_issues": issues,
            "goal": self.ai_prompt_input.toPlainText().strip() or "根据采集结果质量总览修复空值、重复或过长字段",
        },
    )
