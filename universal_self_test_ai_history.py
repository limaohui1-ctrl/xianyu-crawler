"""AI repair history checks for the universal self-test."""

import os

from universal_core import FieldRule, append_ai_repair_history, load_ai_repair_history


def verify_repair_history_flow(window, self_test_stage):
    repair_history_rows = load_ai_repair_history(0)
    if not repair_history_rows or repair_history_rows[0].get("field_count", 0) < 2:
        raise AssertionError("AI 修复历史未保存")
    window.refresh_ai_repair_history()
    if window.ai_repair_history_table.rowCount() < 1:
        raise AssertionError("AI 修复历史未进入 UI")
    repair_history_export = os.path.join(os.getcwd(), "self_test_runtime", "ai_repair_history.csv")
    window.export_ai_repair_history_to_file(repair_history_export)
    if not os.path.exists(repair_history_export):
        raise AssertionError("AI 修复历史导出失败")
    self_test_stage("repair history export OK")

    window.field_table.setRowCount(0)
    window.add_field_row(FieldRule("标题", ".best-title"))
    window.add_field_row(FieldRule("价格", ".best-price"))
    best_history_entry = append_ai_repair_history(
        {
            "time": "2026-06-09 10:10:00",
            "provider_name": "自检厂商",
            "model": "best-model",
            "sample_count": 3,
            "field_count": 2,
            "improved_count": 2,
            "unchanged_count": 0,
            "worse_count": 0,
            "avg_delta": 50,
            "failed_fields": [],
            "field_rules": [rule.to_dict() for rule in window.collect_field_rules_from_table()],
        }
    )
    window.field_table.setRowCount(0)
    window.add_field_row(FieldRule("标题", ".weak-title"))
    append_ai_repair_history(
        {
            "time": "2026-06-09 10:11:00",
            "provider_name": "自检厂商",
            "model": "weak-model",
            "sample_count": 1,
            "field_count": 1,
            "improved_count": 0,
            "unchanged_count": 1,
            "worse_count": 0,
            "avg_delta": 0,
            "failed_fields": ["标题"],
            "field_rules": [rule.to_dict() for rule in window.collect_field_rules_from_table()],
        }
    )
    window.refresh_ai_repair_history()
    window.field_table.setRowCount(0)
    window.add_field_row(FieldRule("标题", ".current-title"))
    window.add_field_row(FieldRule("当前独有", ".current-only"))
    expected_best = best_history_entry
    expected_best_selectors = [rule.selector for rule in window.field_rules_from_history_entry(expected_best)]
    diff_rows = window.compare_ai_repair_history_entry(expected_best)
    diff_changes = {row.get("change") for row in diff_rows}
    if not {"有变化", "历史新增", "历史缺少"}.intersection(diff_changes) or window.ai_repair_diff_table.rowCount() < 1:
        raise AssertionError("AI 修复历史字段差异对比未识别变化")
    title_diff_row = next(
        (
            row
            for row in range(window.ai_repair_diff_table.rowCount())
            if window.ai_repair_diff_table.item(row, 1) and window.ai_repair_diff_table.item(row, 1).text() == "标题"
        ),
        -1,
    )
    if title_diff_row < 0:
        raise AssertionError("AI 修复历史字段差异对比缺少标题字段")
    selected_index = next(
        (index for index, entry in enumerate(getattr(window, "ai_repair_history_entries", [])) if entry is expected_best),
        0,
    )
    window.ai_repair_history_table.setCurrentCell(selected_index, 0)
    window.ai_repair_history_table.selectRow(selected_index)
    window.compare_ai_repair_history_entry(expected_best)
    window.ai_repair_diff_table.clearSelection()
    window.ai_repair_diff_table.setCurrentCell(title_diff_row, 0)
    window.ai_repair_diff_table.selectRow(title_diff_row)
    selected_repair_fields = window.selected_repair_diff_fields()
    if selected_repair_fields != ["标题"]:
        raise AssertionError(f"AI 修复历史差异表选中字段错误：{selected_repair_fields}")
    if not window.apply_repair_history_fields(expected_best, selected_repair_fields):
        raise AssertionError(
            "未能只应用选中的 AI 修复历史字段："
            f"history_row={window.ai_repair_history_table.currentRow()}, "
            f"diff_row={window.ai_repair_diff_table.currentRow()}, "
            f"fields={selected_repair_fields}"
        )
    partial_rules = {rule.name: rule.selector for rule in window.collect_field_rules_from_table()}
    if partial_rules.get("标题") != ".best-title" or partial_rules.get("当前独有") != ".current-only":
        raise AssertionError("只应用选中 AI 修复字段未保留当前字段或未更新目标字段")
    self_test_stage("repair history partial apply OK")

    window.field_table.setRowCount(0)
    window.add_field_row(FieldRule("标题", ".current-title"))
    window.add_field_row(FieldRule("当前独有", ".current-only"))
    if not window.apply_ai_repair_history_entry(expected_best):
        raise AssertionError("未能复用指定最佳 AI 修复历史")
    restored_selectors = [
        window.field_table.item(row, 1).text()
        for row in range(window.field_table.rowCount())
    ]
    if restored_selectors != expected_best_selectors:
        raise AssertionError("最佳 AI 修复历史未恢复最佳字段配置")
    selected_index = next(
        (index for index, entry in enumerate(getattr(window, "ai_repair_history_entries", [])) if entry.get("time") == best_history_entry.get("time")),
        -1,
    )
    if selected_index < 0:
        raise AssertionError("AI 修复历史表未保存可选记录")
    window.ai_repair_history_table.selectRow(selected_index)
    window.field_table.setRowCount(0)
    if not window.apply_selected_ai_repair_history() or window.field_table.item(0, 1).text() != ".best-title":
        raise AssertionError("选中 AI 修复历史未恢复字段配置")
    self_test_stage("repair history reuse OK")
