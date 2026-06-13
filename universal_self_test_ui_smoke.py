"""UI smoke helpers for the universal self-test."""

import json

from universal_core import FIELD_HEADERS, analyze_collect_task, classify_error


def verify_collect_wizard_smoke(window):
    gallery_plan = analyze_collect_task(
        "https://example.com/gallery",
        html="<html><head><title>图片相册</title></head><body>"
        + "".join(f"<img src='/img/{index}.jpg'>" for index in range(12))
        + "</body></html>",
        user_goal="抓取图片",
        preferred_scene="通用自动识别",
    )
    if gallery_plan.get("use_case", {}).get("key") != "vision_file":
        raise AssertionError("图片页面未推荐视觉模型用途")
    form_plan = analyze_collect_task(
        "https://example.com/search",
        html="<html><body><form>" + "".join(f"<input name='q{index}'>" for index in range(5)) + "</form></body></html>",
        user_goal="复杂动态搜索页，需要修复选择器",
        preferred_scene="通用自动识别",
    )
    if form_plan.get("use_case", {}).get("key") != "strong_reasoning":
        raise AssertionError("复杂表单页未推荐强推理模型用途")
    pdf_plan = analyze_collect_task("https://example.com/report.pdf", html="", user_goal="PDF 转表格")
    if pdf_plan.get("use_case", {}).get("key") != "vision_file":
        raise AssertionError("PDF 链接未推荐视觉模型用途")
    if window.latest_preview_rules == [] or window.ai_quality_table.rowCount() < 3:
        raise AssertionError("向导未自动预采并生成字段质量评分")
    if "字段质量评分" not in window.ai_quality_score_label.text():
        raise AssertionError("向导预采后未刷新字段质量评分")
    if not window.prepare_two_click_collect():
        raise AssertionError("2 次点击准备采集失败")
    if "新手流程：" not in window.new_user_flow_label.text() or "2 AI 准备：进行中" not in window.new_user_flow_label.text():
        raise AssertionError("新手流程未展示 AI 准备阶段")
    if window.tabs.tabText(window.tabs.currentIndex()) != "一键采集":
        raise AssertionError("2 次点击准备后不应离开统一普通界面")
    if window.template_combo.currentText() != "电商商品页":
        raise AssertionError("2 次点击准备后未保留推荐模板")
    if window.task_queue_table.rowCount() < 1 or not window.task_queue_rows:
        raise AssertionError("2 次点击准备后未生成任务队列")
    if "2 次点击准备完成" not in window.collect_progress_label.text():
        raise AssertionError("2 次点击准备状态未刷新")
    if "robots.txt" not in window.risk_summary_label.text():
        raise AssertionError("2 次点击准备后未刷新 robots 风险摘要")
    if window.ai_two_click_prepare_button.text() != "AI 一键准备":
        raise AssertionError("一键准备按钮文案不清晰")
    if window.ai_two_click_start_button.text() != "准备并开始采集":
        raise AssertionError("准备并开始按钮缺失")
    start_calls = []
    original_start_collecting_for_two_click = window.start_collecting
    window.start_collecting = lambda: start_calls.append(window.urls_from_input())
    try:
        if not window.prepare_and_start_collect():
            raise AssertionError("准备并开始采集失败")
    finally:
        window.start_collecting = original_start_collecting_for_two_click
    if not start_calls or not start_calls[0]:
        raise AssertionError("准备并开始采集未触发开始采集")
    if "3 开始采集：进行中" not in window.new_user_flow_label.text():
        raise AssertionError("新手流程未展示开始采集阶段")
    preview_columns, preview_rows = window.ai_table_data()
    preview_text = json.dumps({"columns": preview_columns, "rows": preview_rows}, ensure_ascii=False)
    if "商品列表" not in preview_text or "价格" not in preview_text:
        raise AssertionError("向导预采结果未进入 AI 表格")
    if window.result_table.columnCount() != len(FIELD_HEADERS):
        raise AssertionError("结果表字段不完整")
    if classify_error("API 请求失败：HTTP 401 unauthorized").get("category") != "API 配置":
        raise AssertionError("API 错误分类失败")
    if classify_error("Timeout 30000ms exceeded").get("category") != "网络超时":
        raise AssertionError("超时错误分类失败")
    if classify_error("locator.click: waiting for selector").get("category") != "选择器失效":
        raise AssertionError("选择器错误分类失败")
