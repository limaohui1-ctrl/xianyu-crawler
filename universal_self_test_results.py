"""Result workflow checks for the universal self-test."""

from universal_core import FIELD_HEADERS, CollectorDatabase, UniversalExtractor, content_fingerprint


def verify_result_workflow(window, template, html, self_test_stage):
    record = UniversalExtractor(template).extract(html, "https://example.com/item")
    if record["title"] != "测试商品 A":
        raise AssertionError("标题识别失败")
    if "128.50" not in record["price"]:
        raise AssertionError("价格识别失败")
    if record["published_time"] != "2026-06-08":
        raise AssertionError("时间识别失败")
    if record["author"] != "测试作者":
        raise AssertionError("作者识别失败")
    if not record["images"] or record["images"][0]["url"] != "https://example.com/a.jpg":
        raise AssertionError("图片识别失败")
    if not record["links"] or record["links"][0]["url"] != "https://example.com/detail":
        raise AssertionError("链接识别失败")
    if not record["tables"]:
        raise AssertionError("表格识别失败")
    window.add_record(record)
    if "4 导出结果：进行中" not in window.new_user_flow_label.text():
        raise AssertionError("新手流程未展示导出结果阶段")
    export_hint = window.result_export_hint_label.text()
    for expected in ("导出 Excel", "复制到 Sheets", "下载图片"):
        if expected not in export_hint:
            raise AssertionError(f"导出引导缺失：{expected}")
    window.result_table.selectRow(0)
    window.update_current_detail()
    if "测试商品 A" not in window.detail_title_label.text():
        raise AssertionError("详情标题预览失败")
    if window.detail_link_table.rowCount() < 1:
        raise AssertionError("链接展开失败")
    if window.detail_table_view.rowCount() < 1 or window.detail_table_view.columnCount() < 2:
        raise AssertionError("表格展开失败")
    if window.image_layout.count() < 2:
        raise AssertionError("图片缩略图区域未创建条目")

    db = CollectorDatabase()
    first = db.save_record(record, skip_unchanged=True)
    duplicate = db.save_record(dict(record), skip_unchanged=True)
    changed_record = dict(record)
    changed_record["price"] = "￥99.00"
    changed_record["fingerprint"] = content_fingerprint(changed_record)
    second = db.save_record(changed_record, skip_unchanged=True)
    if first.get("changed"):
        raise AssertionError("首次记录不应标记变化")
    if not duplicate.get("duplicate"):
        raise AssertionError("未变化记录未跳过重复入库")
    if not second.get("changed"):
        raise AssertionError("历史变化追踪失败")
    window.clear_current_results()
    if "4 导出结果：完成" in window.new_user_flow_label.text() or "4 导出结果：进行中" in window.new_user_flow_label.text():
        raise AssertionError("清空结果后新手流程仍停留在导出阶段")
    if "采到结果后" not in window.result_export_hint_label.text():
        raise AssertionError("清空结果后导出引导未恢复等待状态")
    self_test_stage("result workflow OK")

    error_record = dict(record)
    error_record["error"] = "HTTP 500"
    for sample in (first, duplicate, second, error_record):
        window.add_record(sample)
    status_column = FIELD_HEADERS.index("是否变化") if "是否变化" in FIELD_HEADERS else FIELD_HEADERS.index("变化")
    expected_statuses = ["新增", "重复", "变化", "错误"]
    actual_statuses = [
        window.result_table.item(row, status_column).text()
        for row in range(window.result_table.rowCount())
    ]
    if actual_statuses != expected_statuses:
        raise AssertionError(f"结果状态列错误：{actual_statuses}")
    self_test_stage("status table OK")
    summary_text = window.result_status_label.text()
    for expected in ("新增 1", "重复 1", "变化 1", "错误 1"):
        if expected not in summary_text:
            raise AssertionError(f"结果状态汇总缺失：{expected}")

    quality_records = [
        {**record, "title": "重复标题", "price": "", "body": "短正文", "error": ""},
        {**record, "title": "重复标题", "price": "", "body": "短正文", "error": ""},
        {**record, "title": "重复标题", "price": "", "body": "超长" * 3000, "error": "HTTP 500"},
    ]
    result_quality = window.analyze_result_quality(quality_records)
    quality_by_field = {item.get("field"): item for item in result_quality}
    if quality_by_field.get("价格", {}).get("status") != "需处理" or "空值率" not in quality_by_field.get("价格", {}).get("problem", ""):
        raise AssertionError("采集结果质量总览未识别高空值字段")
    if quality_by_field.get("标题", {}).get("status") != "需确认" or "重复率" not in quality_by_field.get("标题", {}).get("problem", ""):
        raise AssertionError("采集结果质量总览未识别重复字段")
    if "内容过长" not in quality_by_field.get("正文", {}).get("problem", ""):
        raise AssertionError("采集结果质量总览未识别疑似整页字段")
    if quality_by_field.get("错误", {}).get("status") != "需处理":
        raise AssertionError("采集结果质量总览未识别错误列")
    window.fill_result_quality_table(result_quality)
    if window.result_quality_table.rowCount() < 4 or "需要修复" not in window.result_quality_score_label.text():
        raise AssertionError("采集结果质量总览未进入 UI")
    self_test_stage("result quality OK")
    repair_issues = window.result_quality_issues_for_repair(result_quality)
    if not repair_issues or any(item.get("field") == "错误" for item in repair_issues):
        raise AssertionError("采集结果质量问题未正确转换为字段修复问题")
    captured_repair = []
    original_run_ai_worker = window.run_ai_worker
    original_records_for_quality = list(window.records)
    window.records = list(quality_records)
    window.latest_preview_url = "https://example.com/item"
    window.latest_preview_html = html
    window.run_ai_worker = lambda action, payload=None: captured_repair.append((action, payload or {}))
    try:
        window.ai_repair_from_result_quality()
    finally:
        window.records = original_records_for_quality
        window.run_ai_worker = original_run_ai_worker
    if not captured_repair or captured_repair[0][0] != "repair_fields":
        raise AssertionError("采集结果质量问题未生成 AI 修复任务")
    repair_payload = captured_repair[0][1]
    if not repair_payload.get("quality_issues") or not repair_payload.get("field_rules"):
        raise AssertionError("AI 修复任务缺少质量问题或字段规则")
    repair_fields = {item.get("field") for item in repair_payload.get("quality_issues", [])}
    if "价格" not in repair_fields or "标题" not in repair_fields:
        raise AssertionError("AI 修复任务未包含空值/重复问题字段")
    if window.latest_preview_rules == [] or not window.auto_apply_repair_after_ai:
        raise AssertionError("AI 修复任务未准备自动应用和重新预采状态")
    self_test_stage("repair task payload OK")
    after_quality = [
        {**issue, "status": "正常", "score": 100, "problem": "无", "advice": "可以继续使用"}
        for issue in repair_payload.get("quality_issues", [])
    ]
    report_rows = window.update_repair_quality_report(repair_payload.get("quality_issues", []), after_quality)
    if len(report_rows) < 2 or not all(row.get("result") == "改善" for row in report_rows[:2]):
        raise AssertionError("AI 修复验证报告未识别质量改善")
    if window.repair_quality_report_table.rowCount() < 2 or "已改善" not in window.repair_quality_report_label.text():
        raise AssertionError("AI 修复验证报告未进入 UI")
    self_test_stage("repair quality report OK")
    return {
        "record": record,
        "db": db,
        "first": first,
        "duplicate": duplicate,
        "second": second,
        "repair_payload": repair_payload,
    }
