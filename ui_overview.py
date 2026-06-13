"""Overview dashboard and change-alert notification helpers."""

from ui_registry import register

import os
import time

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QStyle,
    QSystemTrayIcon,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QHeaderView,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,

)

from universal_core import APP_NAME_CN


@register("build_overview_tab")
def build_overview_tab(self):
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(12, 12, 12, 12)
    layout.setSpacing(10)

    hero = QGroupBox("监控概览")
    hero_layout = QVBoxLayout(hero)
    self.overview_product_boundary_label = QLabel("主产品面向所有网站；旧闲鱼入口仅作为兼容模式保留。")
    self.overview_product_boundary_label.setWordWrap(True)
    self.overview_status_label = QLabel("等待加载监控概览")
    self.overview_status_label.setWordWrap(True)
    hero_layout.addWidget(self.overview_product_boundary_label)
    hero_layout.addWidget(self.overview_status_label)
    layout.addWidget(hero)

    metrics_row = QHBoxLayout()
    self.overview_unread_label = QLabel("未读变更：0")
    self.overview_schedule_label = QLabel("计划采集：0")
    self.overview_failed_label = QLabel("异常任务：0")
    self.overview_records_label = QLabel("最近结果：0")
    for label in (
        self.overview_unread_label,
        self.overview_schedule_label,
        self.overview_failed_label,
        self.overview_records_label,
    ):
        card = QGroupBox()
        card_layout = QVBoxLayout(card)
        label.setMinimumWidth(130)
        card_layout.addWidget(label)
        metrics_row.addWidget(card)
    layout.addLayout(metrics_row)

    action_card = QGroupBox("快捷操作")
    action_row = QHBoxLayout(action_card)
    self.overview_new_collect_button = QPushButton("开始新采集")
    self.overview_ai_button = QPushButton("AI 配置/抓取")
    self.overview_alerts_button = QPushButton("查看未读变更")
    self.overview_schedule_button = QPushButton("查看计划采集")
    self.overview_failed_button = QPushButton("查看异常任务")
    self.overview_refresh_button = QPushButton("刷新概览")
    self.overview_new_collect_button.clicked.connect(lambda: self.show_main_tab("批量采集"))
    self.overview_ai_button.clicked.connect(lambda: self.show_main_tab("AI 抓取工作台"))
    self.overview_alerts_button.clicked.connect(lambda: self.show_change_alerts_tab(unread_only=True))
    self.overview_schedule_button.clicked.connect(lambda: self.show_history_section("计划采集"))
    self.overview_failed_button.clicked.connect(lambda: self.show_history_section("任务档案"))
    self.overview_refresh_button.clicked.connect(self.refresh_overview)
    for button in (
        self.overview_new_collect_button,
        self.overview_ai_button,
        self.overview_alerts_button,
        self.overview_schedule_button,
        self.overview_failed_button,
        self.overview_refresh_button,
    ):
        action_row.addWidget(button)
    action_row.addStretch(1)
    layout.addWidget(action_card)

    self.overview_run_table = QTableWidget(0, 6)
    self.overview_run_table.setHorizontalHeaderLabels(["ID", "时间", "状态", "模板", "结果", "备注"])
    self.overview_run_table.verticalHeader().setVisible(False)
    self.overview_run_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
    self.overview_run_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
    self.overview_run_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
    self.overview_run_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
    self.overview_run_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
    self.overview_run_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)

    self.overview_record_table = QTableWidget(0, 5)
    self.overview_record_table.setHorizontalHeaderLabels(["时间", "网址", "模板", "标题", "错误"])
    self.overview_record_table.verticalHeader().setVisible(False)
    self.overview_record_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
    self.overview_record_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
    self.overview_record_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
    self.overview_record_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
    self.overview_record_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)

    tables_split = QSplitter(Qt.Orientation.Horizontal)
    run_box = QGroupBox("最近任务")
    run_layout = QVBoxLayout(run_box)
    run_layout.addWidget(self.overview_run_table)
    record_box = QGroupBox("最近结果")
    record_layout = QVBoxLayout(record_box)
    record_layout.addWidget(self.overview_record_table)
    tables_split.addWidget(run_box)
    tables_split.addWidget(record_box)
    tables_split.setStretchFactor(0, 1)
    tables_split.setStretchFactor(1, 1)
    layout.addWidget(tables_split, 1)

    return page

@register("setup_notification_tray")
def setup_notification_tray(self):
    if not QSystemTrayIcon.isSystemTrayAvailable():
        return
    icon = self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxInformation)
    if icon.isNull():
        icon = QIcon()
    self.tray_icon = QSystemTrayIcon(icon, self)
    self.tray_icon.setToolTip(APP_NAME_CN)
    self.tray_icon.activated.connect(self.on_notification_tray_activated)
    self.tray_icon.show()

@register("on_notification_tray_activated")
def on_notification_tray_activated(self, reason):
    if reason in (
        QSystemTrayIcon.ActivationReason.Trigger,
        QSystemTrayIcon.ActivationReason.DoubleClick,
    ):
        self.show_change_alerts_tab(unread_only=True)

@register("show_change_alerts_tab")
def show_change_alerts_tab(self, unread_only=False):
    self.show_history_section("变更提醒")
    if unread_only and hasattr(self, "change_alert_filter_combo"):
        self.change_alert_filter_combo.setCurrentText("未读")
    self.show()
    self.raise_()
    self.activateWindow()

@register("notify_unread_change_alerts")
def notify_unread_change_alerts(self, unread_count, latest_alert=None):
    latest_alert = latest_alert or {}
    notice_key = f"{unread_count}:{latest_alert.get('ID', '')}"
    if unread_count <= 0 or notice_key == self.last_unread_alert_notice_key:
        return False
    self.last_unread_alert_notice_key = notice_key
    self.last_unread_alert_notice_count = unread_count
    message = (
        f"发现 {unread_count} 条未读网页变更。"
        f"{latest_alert.get('字段', '')}：{latest_alert.get('旧值', '')} -> {latest_alert.get('新值', '')}"
    )
    self.notification_events.append(
        {
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "count": unread_count,
            "id": latest_alert.get("ID", ""),
            "message": message,
        }
    )
    self.append_log(f"[变更通知] {message}")
    if os.environ.get("UNIVERSAL_COLLECTOR_SELF_TEST") == "1":
        return True
    if self.tray_icon:
        self.tray_icon.showMessage(
            "网页变更提醒",
            message,
            QSystemTrayIcon.MessageIcon.Information,
            8000,
        )
    return True

@register("overview_metrics")
def overview_metrics(self):
    alerts = getattr(self, "change_alert_rows", []) or []
    schedules = getattr(self, "schedules", []) or []
    runs = getattr(self, "run_records", []) or self.database.recent_runs(20)
    records = getattr(self, "history_records", []) or self.database.recent_records(50)
    unread_alerts = [item for item in alerts if item.get("处理状态") == "未读"]
    enabled_schedules = [item for item in schedules if item.get("enabled")]
    failed_runs = [
        item for item in runs
        if item.get("status") in {"failed", "partial", "stopped"}
    ]
    errored_records = [item for item in records if item.get("error")]
    return {
        "unread_alerts": unread_alerts,
        "schedule_count": len(schedules),
        "enabled_schedule_count": len(enabled_schedules),
        "failed_runs": failed_runs,
        "record_count": len(records),
        "errored_records": errored_records,
        "runs": runs,
        "records": records,
    }

@register("fill_overview_run_table")
def fill_overview_run_table(self, runs):
    if not hasattr(self, "overview_run_table"):
        return
    self.overview_run_table.setRowCount(0)
    for run in (runs or [])[:8]:
        row = self.overview_run_table.rowCount()
        self.overview_run_table.insertRow(row)
        values = [
            run.get("id", ""),
            run.get("started_at", ""),
            self.run_status_text(run.get("status", "")),
            run.get("template_name", ""),
            run.get("result_count", 0),
            run.get("notes", ""),
        ]
        for column, value in enumerate(values):
            item = QTableWidgetItem(str(value))
            item.setToolTip(str(value))
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if column == 2 and run.get("status") in {"failed", "partial", "stopped"}:
                item.setBackground(Qt.GlobalColor.yellow)
            self.overview_run_table.setItem(row, column, item)

@register("fill_overview_record_table")
def fill_overview_record_table(self, records):
    if not hasattr(self, "overview_record_table"):
        return
    self.overview_record_table.setRowCount(0)
    for record in (records or [])[:8]:
        row = self.overview_record_table.rowCount()
        self.overview_record_table.insertRow(row)
        values = [
            record.get("collected_at", ""),
            record.get("url", ""),
            record.get("template_name", ""),
            record.get("title", ""),
            record.get("error", ""),
        ]
        for column, value in enumerate(values):
            item = QTableWidgetItem(str(value))
            item.setToolTip(str(value))
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if column == 4 and value:
                item.setBackground(Qt.GlobalColor.yellow)
            self.overview_record_table.setItem(row, column, item)

@register("refresh_overview")
def refresh_overview(self):
    if not hasattr(self, "overview_status_label"):
        return
    metrics = self.overview_metrics()
    unread_count = len(metrics["unread_alerts"])
    failed_count = len(metrics["failed_runs"])
    errored_count = len(metrics["errored_records"])
    self.overview_unread_label.setText(f"未读变更：{unread_count}")
    self.overview_schedule_label.setText(
        f"计划采集：{metrics['enabled_schedule_count']}/{metrics['schedule_count']}"
    )
    self.overview_failed_label.setText(f"异常任务：{failed_count}")
    self.overview_records_label.setText(f"最近结果：{metrics['record_count']}")
    self.overview_status_label.setText(
        "概览已刷新："
        f"未读变更 {unread_count}，异常任务 {failed_count}，结果错误 {errored_count}。"
    )
    self.fill_overview_run_table(metrics["runs"])
    self.fill_overview_record_table(metrics["records"])
