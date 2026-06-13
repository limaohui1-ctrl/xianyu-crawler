"""Schedule table, persistence, and due-run helpers."""

from ui_registry import register

import time

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import QMessageBox, QTableWidgetItem

from universal_core import (
    DEFAULT_PAGE_LIMIT,
    DEFAULT_SCROLL_TIMES,
    new_schedule_item,
    safe_int,
    save_schedules,
    schedule_next_run_text,
)
from core_firecrawl import (
    safe_int,
)



@register("show_schedule_hint")
def show_schedule_hint(self):
    minutes, ok = self.simple_int_dialog("计划采集", "每隔多少分钟自动采集一次当前任务？", 30, 1, 1440)
    if not ok:
        return
    self.add_schedule_from_current_config(minutes=minutes)

@register("save_schedule_state")
def save_schedule_state(self):
    self.schedules = save_schedules(self.schedules)
    if hasattr(self, "schedule_table"):
        self.fill_schedule_table()
    self.refresh_overview()

@register("fill_schedule_table")
def fill_schedule_table(self):
    if not hasattr(self, "schedule_table"):
        return
    selected_id = ""
    selected_index = self.selected_schedule_index()
    if selected_index >= 0 and selected_index < len(self.schedules):
        selected_id = self.schedules[selected_index].get("id", "")
    self.schedule_table.setRowCount(0)
    for source in self.schedules or []:
        row = self.schedule_table.rowCount()
        self.schedule_table.insertRow(row)
        config = source.get("config") or {}
        urls = config.get("urls") or []
        values = [
            "启用" if source.get("enabled") else "停用",
            source.get("name", ""),
            f"{source.get('interval_minutes', 0)} 分钟",
            source.get("next_run_at", ""),
            source.get("last_run_at", ""),
            source.get("run_count", 0),
            source.get("last_status", ""),
            len(urls),
            source.get("id", ""),
        ]
        for column, value in enumerate(values):
            item = QTableWidgetItem(str(value))
            item.setToolTip(str(value))
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.schedule_table.setItem(row, column, item)
        if selected_id and source.get("id") == selected_id:
            self.schedule_table.selectRow(row)

@register("selected_schedule_index")
def selected_schedule_index(self):
    if not hasattr(self, "schedule_table"):
        return -1
    selected = self.schedule_table.selectionModel().selectedRows()
    if not selected:
        return -1
    schedule_id_item = self.schedule_table.item(selected[0].row(), 8)
    schedule_id = schedule_id_item.text() if schedule_id_item else ""
    for index, source in enumerate(self.schedules or []):
        if source.get("id") == schedule_id:
            return index
    return -1

@register("add_schedule_from_current_config")
def add_schedule_from_current_config(self, minutes=None):
    urls = self.urls_from_input()
    if not urls:
        QMessageBox.information(self, "提示", "请先输入至少一个网址。")
        return None
    if minutes is None:
        minutes, ok = self.simple_int_dialog("新增计划采集", "每隔多少分钟自动采集一次当前任务？", 30, 1, 1440)
        if not ok:
            return None
    config = self.current_run_config(urls)
    name = f"{self.selected_template_name()}｜{len(urls)} 个网址"
    item = new_schedule_item(name, int(minutes or 30), config)
    self.schedules.append(item)
    self.save_schedule_state()
    self.show_history_section("计划采集")
    self.append_ai_output(f"已新增计划采集：{item['name']}，每 {item['interval_minutes']} 分钟运行一次。")
    return item

@register("toggle_selected_schedule")
def toggle_selected_schedule(self):
    index = self.selected_schedule_index()
    if index < 0:
        QMessageBox.information(self, "提示", "请先选择一个计划采集任务。")
        return
    self.schedules[index]["enabled"] = not bool(self.schedules[index].get("enabled"))
    self.schedules[index]["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    state = "启用" if self.schedules[index]["enabled"] else "停用"
    self.save_schedule_state()
    self.append_ai_output(f"计划采集已{state}：{self.schedules[index].get('name', '')}")

@register("delete_selected_schedule")
def delete_selected_schedule(self):
    index = self.selected_schedule_index()
    if index < 0:
        QMessageBox.information(self, "提示", "请先选择一个计划采集任务。")
        return
    removed = self.schedules.pop(index)
    self.save_schedule_state()
    self.append_ai_output(f"已删除计划采集：{removed.get('name', '')}")

@register("apply_schedule_config_to_ui")
def apply_schedule_config_to_ui(self, schedule):
    config = (schedule or {}).get("config") or {}
    urls = config.get("urls") or []
    if urls:
        self.url_input.setPlainText("\n".join(urls))
        self.ai_url_input.setText(urls[0])
        self.pick_url_input.setText(urls[0])
    template_name = config.get("template_name", "")
    if template_name:
        index = self.template_combo.findText(template_name)
        if index >= 0:
            self.template_combo.setCurrentIndex(index)
    self.use_browser_checkbox.setChecked(bool(config.get("use_browser", True)))
    self.scroll_times_input.setValue(safe_int(config.get("scroll_times"), DEFAULT_SCROLL_TIMES, self.scroll_times_input.minimum(), self.scroll_times_input.maximum()))
    self.page_limit_input.setValue(safe_int(config.get("page_limit"), DEFAULT_PAGE_LIMIT, self.page_limit_input.minimum(), self.page_limit_input.maximum()))
    self.delay_input.setValue(safe_int(config.get("delay_seconds"), 1, self.delay_input.minimum(), self.delay_input.maximum()))
    self.keep_login_checkbox.setChecked(bool(config.get("keep_login_state", False)))
    self.skip_unchanged_checkbox.setChecked(bool(config.get("skip_unchanged", True)))
    self.subpage_checkbox.setChecked(bool(config.get("scrape_subpages", False)))
    self.subpage_limit_input.setValue(safe_int(config.get("subpage_limit"), 0, self.subpage_limit_input.minimum(), self.subpage_limit_input.maximum()))
    self.selected_subpage_urls = list(config.get("selected_subpage_urls") or [])
    self.apply_firecrawl_config_to_ui(config.get("firecrawl", {}))

@register("mark_schedule_run")
def mark_schedule_run(self, schedule_id, status, message="", count_run=False):
    for source in self.schedules:
        if source.get("id") != schedule_id:
            continue
        source["last_run_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        source["next_run_at"] = schedule_next_run_text(source.get("interval_minutes", 30))
        if count_run:
            source["run_count"] = int(source.get("run_count") or 0) + 1
        source["last_status"] = status
        source["last_message"] = message
        source["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        break
    self.save_schedule_state()

@register("run_schedule")
def run_schedule(self, schedule):
    schedule_id = (schedule or {}).get("id", "")
    if self.worker:
        self.mark_schedule_run(schedule_id, "已跳过", "已有采集任务正在运行")
        self.append_log("已有采集任务正在运行，本次计划采集已跳过。")
        return False
    try:
        self.apply_schedule_config_to_ui(schedule)
        self.active_schedule_id = schedule_id
        try:
            self.start_collecting(skip_confirmation=True)
        except TypeError as start_exc:
            if "skip_confirmation" not in str(start_exc):
                raise
            self.start_collecting()
    except Exception as exc:
        self.active_schedule_id = ""
        self.mark_schedule_run(schedule_id, "启动失败", str(exc))
        self.append_log(f"计划采集启动失败：{exc}")
        return False
    if not self.worker:
        self.active_schedule_id = ""
        self.mark_schedule_run(schedule_id, "未启动", "计划配置未能启动采集")
        self.append_log("计划采集未启动，已保留原计划等待下次检查。")
        return False
    self.mark_schedule_run(schedule_id, "已触发", "计划采集已启动")
    return True

@register("run_selected_schedule_now")
def run_selected_schedule_now(self):
    index = self.selected_schedule_index()
    if index < 0:
        QMessageBox.information(self, "提示", "请先选择一个计划采集任务。")
        return
    self.run_schedule(dict(self.schedules[index]))

@register("start_schedule_tick")
def start_schedule_tick(self):
    if self.schedule_tick_timer:
        self.schedule_tick_timer.stop()
    self.schedule_tick_timer = QTimer(self)
    self.schedule_tick_timer.timeout.connect(self.check_due_schedules)
    self.schedule_tick_timer.start(60 * 1000)

@register("check_due_schedules")
def check_due_schedules(self):
    if self.worker:
        return
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    for source in list(self.schedules or []):
        if not source.get("enabled"):
            continue
        next_run = source.get("next_run_at") or ""
        if not next_run or next_run <= now:
            self.run_schedule(dict(source))
            return
    for topic in self.database.due_memory_topics(time.time(), 10):
        if self.run_memory_topic_sync_by_id(topic.get("id")):
            return
