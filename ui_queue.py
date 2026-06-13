"""Queue management helpers."""

from ui_registry import register

import time

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QClipboard
from PyQt6.QtWidgets import QApplication, QMessageBox, QTableWidgetItem

from universal_core import classify_error

@register("task_queue_snapshot")
def task_queue_snapshot(self):
    snapshot = []
    for source in self.task_queue_rows:
        error_info = classify_error(source.get("error", ""))
        item = {
            "status": str(source.get("status", "")),
            "type": str(source.get("type", "")),
            "stage": str(source.get("stage", "")),
            "url": str(source.get("url", "")),
            "result_count": int(source.get("result_count") or 0),
            "error": str(source.get("error", "")),
            "error_category": str(source.get("error_category") or error_info.get("category", "")),
            "error_advice": str(source.get("error_advice") or error_info.get("advice", "")),
        }
        if any(item.values()):
            snapshot.append(item)
    return snapshot

@register("persist_current_run_queue_snapshot")
def persist_current_run_queue_snapshot(self):
    if not self.current_run_id:
        return
    config = self.database.run_config(self.current_run_id)
    if not config:
        config = self.current_run_config(self.urls_from_input())
    config["task_queue_snapshot"] = self.task_queue_snapshot()
    config["task_queue_saved_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    self.database.update_run_config(self.current_run_id, config)

@register("estimated_task_queue")
def estimated_task_queue(self, urls=None, runtime_overrides=None):
    urls = urls or self.urls_from_input()
    runtime_overrides = runtime_overrides or {}
    queue = []
    page_limit = self.page_limit_input.value()
    scrape_subpages = bool(runtime_overrides.get("scrape_subpages", self.subpage_checkbox.isChecked()))
    subpage_limit = int(runtime_overrides.get("subpage_limit", self.subpage_limit_input.value()) or 0)
    selected_subpages = runtime_overrides.get(
        "selected_subpage_urls",
        self.selected_subpage_urls if self.subpage_checkbox.isChecked() else [],
    )
    follow_link_content = bool(runtime_overrides.get("follow_link_content", False))
    follow_link_limit = int(runtime_overrides.get("follow_link_limit", 0) or 0)
    filter_pdf_media_links = bool(runtime_overrides.get("filter_pdf_media_links", False))
    for url in urls:
        queue.append({"status": "待处理", "type": "主页", "stage": "等待采集", "url": url})
        for page_index in range(2, page_limit + 1):
            queue.append({"status": "预估", "type": "分页", "stage": f"可能第 {page_index} 页", "url": url})
        if selected_subpages:
            for subpage_url in selected_subpages:
                queue.append({"status": "待处理", "type": "已选子页面", "stage": "等待深抓", "url": subpage_url})
        elif scrape_subpages and subpage_limit > 0:
            stage = f"最多 {subpage_limit} 个"
            if runtime_overrides.get("simple_auto_subpages"):
                stage = f"普通模式轻量补全，{stage}"
            queue.append({"status": "预估", "type": "自动子页面", "stage": stage, "url": url})
        if follow_link_content and follow_link_limit > 0:
            link_stage = f"正文跟进 {follow_link_limit} 个"
            if filter_pdf_media_links:
                link_stage += "｜过滤PDF/图片"
            else:
                queue.append({"status": "预估", "type": "PDF文档", "stage": "发现网页内PDF时自动入队解析", "url": url})
            queue.append({"status": "预估", "type": "详情链接正文", "stage": link_stage, "url": url})
    return queue

@register("filtered_task_queue_rows")
def filtered_task_queue_rows(self):
    status_filter = self.task_queue_status_filter.currentText() if hasattr(self, "task_queue_status_filter") else "全部状态"
    type_filter = self.task_queue_type_filter.currentText() if hasattr(self, "task_queue_type_filter") else "全部类型"
    rows = []
    for source in self.task_queue_rows:
        status = source.get("status", "")
        item_type = source.get("type", "")
        if status_filter == "未完成":
            if status in ("已完成",):
                continue
        elif status_filter != "全部状态" and status != status_filter:
            continue
        if type_filter != "全部类型" and item_type != type_filter:
            continue
        rows.append(source)
    return rows

@register("apply_task_queue_filters")
def apply_task_queue_filters(self):
    self.task_queue_table.setRowCount(0)
    for source in self.filtered_task_queue_rows():
        row = self.task_queue_table.rowCount()
        self.task_queue_table.insertRow(row)
        values = [
            source.get("status", ""),
            source.get("type", ""),
            source.get("stage", ""),
            source.get("url", ""),
            source.get("result_count", 0),
            source.get("error_category", ""),
            source.get("error_advice", ""),
            source.get("error", ""),
        ]
        for column, value in enumerate(values):
            item = QTableWidgetItem(str(value))
            item.setToolTip(str(value))
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if column == 0 and source.get("status") == "失败":
                item.setBackground(Qt.GlobalColor.yellow)
            elif column == 0 and source.get("status") == "运行中":
                item.setBackground(Qt.GlobalColor.cyan)
            self.task_queue_table.setItem(row, column, item)
    self.update_queue_summary()
    self.update_queue_detail_panel()

@register("queue_status_counts")
def queue_status_counts(self):
    counts = {}
    for source in self.task_queue_rows:
        status = source.get("status", "") or "未知"
        counts[status] = counts.get(status, 0) + 1
    return counts

@register("update_queue_summary")
def update_queue_summary(self):
    if not hasattr(self, "queue_summary_label"):
        return
    counts = self.queue_status_counts()
    total = len(self.task_queue_rows)
    visible = self.task_queue_table.rowCount() if hasattr(self, "task_queue_table") else total
    parts = [
        f"队列：{total} 项",
        f"当前显示 {visible} 项",
        f"运行中 {counts.get('运行中', 0)}",
        f"失败 {counts.get('失败', 0)}",
        f"未完成 {sum(count for status, count in counts.items() if status not in ('已完成',))}",
    ]
    self.queue_summary_label.setText(" | ".join(parts))
    self.refresh_failure_recovery_panel(counts)

@register("refresh_failure_recovery_panel")
def refresh_failure_recovery_panel(self, counts=None):
    if not hasattr(self, "failure_recovery_label"):
        return
    counts = counts or self.queue_status_counts()
    failed_count = counts.get("失败", 0)
    incomplete_count = sum(count for status, count in counts.items() if status not in ("已完成",))
    if not failed_count:
        self.failure_recovery_label.setText("失败自恢复：暂无失败项")
        return
    failed_rows = [row for row in self.task_queue_rows if row.get("status") == "失败"]
    categories = []
    for row in failed_rows:
        category = row.get("error_category") or classify_error(row.get("error", "")).get("category", "")
        if category and category not in categories:
            categories.append(category)
    category_text = "、".join(categories[:3]) if categories else "未知错误"
    self.failure_recovery_label.setText(
        f"失败自恢复：失败 {failed_count} 项，未完成 {incomplete_count} 项；主要问题：{category_text}。可重试失败项、复制错误、启用真实浏览器或调低速度。"
    )

@register("enable_browser_recovery")
def enable_browser_recovery(self):
    self.use_browser_checkbox.setChecked(True)
    self.append_log("失败自恢复：已启用真实浏览器采集。")
    self.refresh_failure_recovery_panel()
    return True

@register("slow_down_recovery")
def slow_down_recovery(self):
    next_delay = max(3, int(self.delay_input.value() or 0) + 2)
    self.delay_input.setValue(min(next_delay, self.delay_input.maximum()))
    self.append_log(f"失败自恢复：已将访问间隔调低到 {self.delay_input.value()} 秒。")
    self.refresh_failure_recovery_panel()
    return True

@register("selected_queue_row_data")
def selected_queue_row_data(self, table=None):
    table = table or self.task_queue_table
    selected_rows = sorted({index.row() for index in table.selectedIndexes()})
    if not selected_rows:
        return {}
    row = selected_rows[0]
    keys = ["status", "type", "stage", "url", "result_count", "error_category", "error_advice", "error"]
    data = {}
    for column, key in enumerate(keys):
        item = table.item(row, column)
        data[key] = item.text() if item else ""
    return data

@register("update_queue_detail_panel")
def update_queue_detail_panel(self):
    if not hasattr(self, "queue_detail_output"):
        return
    data = self.selected_queue_row_data(self.task_queue_table) if hasattr(self, "task_queue_table") else {}
    if not data:
        self.queue_detail_title_label.setText("未选择队列项")
        self.queue_detail_output.setPlainText("选择一条运行队列后，这里会显示失败原因、建议和原始错误。")
        return
    title = f"{data.get('status') or '未知'} | {data.get('type') or '未知类型'} | {data.get('url') or '无网址'}"
    self.queue_detail_title_label.setText(title)
    lines = [
        f"阶段：{data.get('stage', '')}",
        f"结果数：{data.get('result_count', '')}",
        f"错误类型：{data.get('error_category', '') or '无'}",
        f"处理建议：{data.get('error_advice', '') or '暂无，继续观察或查看原始错误。'}",
        f"原始错误：{data.get('error', '') or '无'}",
    ]
    self.queue_detail_output.setPlainText("\n".join(lines))

@register("fill_queue_snapshot_table")
def fill_queue_snapshot_table(self, table, rows, records=None):
    record_map = self.queue_record_summary(records or [])
    table.setRowCount(0)
    columns = ["status", "type", "stage", "url", "result_count", "error_category", "error_advice", "error"]
    for source in rows or []:
        source = dict(source)
        summary = record_map.get(source.get("url", ""), {})
        source["result_count"] = int(source.get("result_count") or summary.get("result_count") or 0)
        source["error"] = source.get("error") or summary.get("error", "")
        error_info = classify_error(source.get("error", ""))
        source["error_category"] = source.get("error_category") or error_info.get("category", "")
        source["error_advice"] = source.get("error_advice") or error_info.get("advice", "")
        row = table.rowCount()
        table.insertRow(row)
        for column, key in enumerate(columns):
            value = source.get(key, "")
            item = QTableWidgetItem(str(value))
            item.setToolTip(str(value))
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            table.setItem(row, column, item)

@register("fill_task_queue_table")
def fill_task_queue_table(self, rows):
    self.task_queue_rows = [dict(row) for row in rows]
    self.apply_task_queue_filters()

@register("queue_record_summary")
def queue_record_summary(self, records):
    summary = {}
    for record in records or []:
        url = record.get("url", "")
        if not url:
            continue
        item = summary.setdefault(url, {"result_count": 0, "error": ""})
        item["result_count"] += 1
        if record.get("error") and not item["error"]:
            item["error"] = record.get("error", "")
    return summary

@register("update_queue_result_summary_for_record")
def update_queue_result_summary_for_record(self, record):
    url = record.get("url", "")
    if not url:
        return
    changed = False
    for source in self.task_queue_rows:
        if source.get("url") != url:
            continue
        source["result_count"] = int(source.get("result_count") or 0) + 1
        if record.get("error"):
            error_info = classify_error(record.get("error", ""))
            source["error"] = record.get("error", "")
            source["error_category"] = error_info.get("category", "")
            source["error_advice"] = error_info.get("advice", "")
            source["status"] = "失败"
        changed = True
        break
    if not changed:
        error_info = classify_error(record.get("error", ""))
        self.task_queue_rows.append(
            {
                "status": "失败" if record.get("error") else "已完成",
                "type": "实际",
                "stage": "结果入库",
                "url": url,
                "result_count": 1,
                "error": record.get("error", ""),
                "error_category": error_info.get("category", ""),
                "error_advice": error_info.get("advice", ""),
            }
        )
    self.apply_task_queue_filters()
    self.persist_current_run_queue_snapshot()

@register("select_record_by_url")
def select_record_by_url(self, table, url):
    for row in range(table.rowCount()):
        item = table.item(row, 1)
        if item and item.text() == url:
            table.selectRow(row)
            return True
    return False

@register("selected_queue_url")
def selected_queue_url(self, table):
    selected_rows = sorted({index.row() for index in table.selectedIndexes()})
    if not selected_rows:
        return ""
    item = table.item(selected_rows[0], 3)
    return item.text() if item else ""

@register("selected_queue_error_text")
def selected_queue_error_text(self, table=None):
    data = self.selected_queue_row_data(table or self.task_queue_table)
    return data.get("error", "")

@register("view_selected_queue_result")
def view_selected_queue_result(self):
    url = self.selected_queue_url(self.task_queue_table)
    if not url:
        QMessageBox.information(self, "提示", "请先选择一个队列项。")
        return
    if not self.select_record_by_url(self.result_table, url):
        QMessageBox.information(self, "提示", "当前结果表里还没有这个队列项的结果。")
        return
    self.update_current_detail()

@register("retry_selected_queue_item")
def retry_selected_queue_item(self):
    url = self.selected_queue_url(self.task_queue_table)
    if not url:
        QMessageBox.information(self, "提示", "请先选择一个队列项。")
        return
    self.url_input.setPlainText(url)
    self.append_log(f"已准备重试选中队列项：{url}")
    self.start_collecting()

@register("copy_selected_queue_error")
def copy_selected_queue_error(self):
    data = self.selected_queue_row_data(self.task_queue_table)
    if not data:
        QMessageBox.information(self, "提示", "请先选择一个队列项。")
        return
    text = "\n".join(
        [
            f"网址：{data.get('url', '')}",
            f"状态：{data.get('status', '')}",
            f"阶段：{data.get('stage', '')}",
            f"错误类型：{data.get('error_category', '')}",
            f"建议：{data.get('error_advice', '')}",
            f"原始错误：{data.get('error', '')}",
        ]
    )
    clipboard = QApplication.clipboard()
    clipboard.clear()
    clipboard.setText(text, mode=QClipboard.Mode.Clipboard)
    self.last_clipboard_text = text
    QApplication.processEvents()
    self.append_log("已复制队列错误详情。")

@register("incomplete_queue_urls")
def incomplete_queue_urls(self):
    urls = []
    seen = set()
    for source in self.task_queue_rows:
        status = source.get("status", "")
        url = source.get("url", "")
        if not url or status == "已完成":
            continue
        if status not in ("失败", "运行中"):
            continue
        if url in seen:
            continue
        seen.add(url)
        urls.append(url)
    return urls

@register("has_timeout_queue_failure")
def has_timeout_queue_failure(self):
    for source in self.task_queue_rows:
        if source.get("status") != "失败":
            continue
        category = source.get("error_category") or classify_error(source.get("error", "")).get("category", "")
        if category == "网络超时":
            return True
    return False

@register("retry_incomplete_queue_items")
def retry_incomplete_queue_items(self):
    urls = self.incomplete_queue_urls()
    if not urls:
        QMessageBox.information(self, "提示", "当前队列没有失败或未完成的网址。")
        return
    self.url_input.setPlainText("\n".join(urls))
    self.append_log(f"已准备重试 {len(urls)} 个失败/未完成网址。")
    self.start_collecting()

@register("estimate_current_task")
def estimate_current_task(self):
    urls = self.urls_from_input()
    if not urls:
        QMessageBox.information(self, "提示", "请先输入至少一个网址。")
        return
    queue = self.estimated_task_queue(urls)
    self.fill_task_queue_table(queue)
    self.append_log(f"任务预估完成：约 {len(queue)} 个队列项。")
    self.update_collect_progress(
        {
            "processed": 0,
            "success": 0,
            "failed": 0,
            "total": len(queue),
            "current_url": urls[0],
            "stage": "任务预估",
            "status": "planned",
        }
    )

@register("update_collect_progress")
def update_collect_progress(self, progress):
    progress = progress or {}
    self.current_run_progress = progress
    processed = int(progress.get("processed") or 0)
    success = int(progress.get("success") or 0)
    failed = int(progress.get("failed") or 0)
    total = int(progress.get("total") or 0)
    current_url = progress.get("current_url", "")
    stage = progress.get("stage", "")
    if total > 0:
        self.collect_progress_bar.setRange(0, total)
        self.collect_progress_bar.setValue(min(processed, total))
        total_text = str(total)
    else:
        self.collect_progress_bar.setRange(0, 100)
        self.collect_progress_bar.setValue(0)
        total_text = "未知"
    label = f"进度：已处理 {processed}/{total_text}，成功 {success}，失败 {failed}"
    if stage:
        label += f"，阶段：{stage}"
    if current_url:
        label += f"，当前：{current_url}"
    self.collect_progress_label.setText(label)
    if hasattr(self, "simple_progress_label"):
        if total > 0:
            simple_label = f"后台采集中：已处理 {processed}/{total_text}，成功 {success}，失败 {failed}"
        else:
            simple_label = "后台采集中：正在读取网页"
        if stage:
            simple_label += f"；{stage}"
        if failed > 0:
            simple_label += "；有网页没读成功，成功结果已保留，可点重试失败"
            if self.has_timeout_queue_failure():
                simple_label += "，网站可能较慢"
        self.simple_progress_label.setText(simple_label)
        self.set_simple_flow_step("采集")
    if hasattr(self, "simple_status_label"):
        if progress.get("status") in {"finished", "partial", "failed", "stopped"}:
            self.simple_status_label.setText("采集结束，可以导出结果")
        else:
            self.simple_status_label.setText("后台正在采集，复杂步骤已自动处理")
    if current_url or stage:
        self.update_task_queue_progress(progress)

@register("update_task_queue_progress")
def update_task_queue_progress(self, progress):
    stage = progress.get("stage", "")
    current_url = progress.get("current_url", "")
    if not current_url and not stage:
        return
    matched_index = -1
    for index, source in enumerate(self.task_queue_rows):
        if current_url and source.get("url") == current_url:
            matched_index = index
            break
    failed = bool(progress.get("failed_item") or progress.get("current_failed"))
    if stage.endswith("完成") or stage == "采集结束":
        status = "失败" if failed else "已完成"
    else:
        status = "运行中"
    if matched_index < 0:
        self.task_queue_rows.append(
            {"status": status, "type": "实际", "stage": stage, "url": current_url}
        )
        self.apply_task_queue_filters()
        return
    self.task_queue_rows[matched_index]["status"] = status
    self.task_queue_rows[matched_index]["stage"] = stage
    if current_url:
        self.task_queue_rows[matched_index]["url"] = current_url
    self.apply_task_queue_filters()
    self.persist_current_run_queue_snapshot()
