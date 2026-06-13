"""Task tab construction for the universal UI."""

from ui_registry import register

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QHeaderView,
    QCheckBox,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,

)

from universal_core import DEFAULT_PAGE_LIMIT, DEFAULT_SCROLL_TIMES
from ui_firecrawl import add_firecrawl_controls_to_task_layout, build_firecrawl_controls


@register("build_task_tab")
def build_task_tab(self):
    page = QWidget()
    layout = QVBoxLayout(page)

    top_splitter = QSplitter(Qt.Orientation.Horizontal)
    task_box = QGroupBox("通用采集任务中心")
    task_layout = QGridLayout(task_box)

    self.url_input = QTextEdit()
    self.url_input.setPlaceholderText("每行一个网址，例如：https://example.com/article/1")
    self.url_input.setPlainText("https://example.com/")
    self.import_url_button = QPushButton("导入网址")
    self.import_url_button.clicked.connect(self.import_urls)
    self.template_combo = QComboBox()
    self.use_browser_checkbox = QCheckBox("使用真实浏览器采集动态网页")
    self.use_browser_checkbox.setChecked(True)
    self.keep_login_checkbox = QCheckBox("保留登录状态")
    self.skip_unchanged_checkbox = QCheckBox("跳过未变化重复记录")
    self.skip_unchanged_checkbox.setChecked(True)
    self.subpage_checkbox = QCheckBox("抓取同站子页面")
    build_firecrawl_controls(self)
    self.subpage_limit_input = QSpinBox()
    self.subpage_limit_input.setRange(0, 100)
    self.subpage_limit_input.setValue(0)
    self.scroll_times_input = QSpinBox()
    self.scroll_times_input.setRange(0, 20)
    self.scroll_times_input.setValue(DEFAULT_SCROLL_TIMES)
    self.page_limit_input = QSpinBox()
    self.page_limit_input.setRange(1, 50)
    self.page_limit_input.setValue(DEFAULT_PAGE_LIMIT)
    self.delay_input = QSpinBox()
    self.delay_input.setRange(1, 60)
    self.delay_input.setValue(1)
    self.delay_input.setSuffix(" 秒")

    self.start_button = QPushButton("开始采集")
    self.stop_button = QPushButton("停止")
    self.estimate_task_button = QPushButton("预估任务")
    self.risk_check_button = QPushButton("抓取前检查")
    self.auto_fix_preflight_button = QPushButton("开始前自动修复")
    self.login_browser_button = QPushButton("打开登录浏览器")
    self.stop_button.setEnabled(False)
    self.start_button.clicked.connect(self.start_collecting)
    self.stop_button.clicked.connect(self.stop_collecting)
    self.estimate_task_button.clicked.connect(self.estimate_current_task)
    self.risk_check_button.clicked.connect(self.run_preflight_check)
    self.auto_fix_preflight_button.clicked.connect(self.auto_fix_before_start)
    self.login_browser_button.clicked.connect(self.open_login_browser)

    task_layout.addWidget(QLabel("网址列表"), 0, 0)
    task_layout.addWidget(self.url_input, 1, 0, 1, 4)
    task_layout.addWidget(self.import_url_button, 2, 0)
    task_layout.addWidget(QLabel("模板"), 2, 1)
    task_layout.addWidget(self.template_combo, 2, 2)
    task_layout.addWidget(self.use_browser_checkbox, 2, 3)
    task_layout.addWidget(QLabel("滚动次数"), 3, 0)
    task_layout.addWidget(self.scroll_times_input, 3, 1)
    task_layout.addWidget(QLabel("翻页上限"), 3, 2)
    task_layout.addWidget(self.page_limit_input, 3, 3)
    task_layout.addWidget(QLabel("访问间隔"), 4, 0)
    task_layout.addWidget(self.delay_input, 4, 1)
    task_layout.addWidget(self.start_button, 4, 2)
    task_layout.addWidget(self.stop_button, 4, 3)
    task_layout.addWidget(self.keep_login_checkbox, 5, 0)
    task_layout.addWidget(self.skip_unchanged_checkbox, 5, 1)
    task_layout.addWidget(self.estimate_task_button, 5, 2)
    task_layout.addWidget(self.login_browser_button, 5, 3)
    task_layout.addWidget(self.subpage_checkbox, 6, 0)
    task_layout.addWidget(QLabel("子页面上限"), 6, 1)
    task_layout.addWidget(self.subpage_limit_input, 6, 2)
    task_layout.addWidget(self.risk_check_button, 6, 3)
    add_firecrawl_controls_to_task_layout(self, task_layout, self.auto_fix_preflight_button)

    preview_box = QGroupBox("采集日志")
    preview_layout = QVBoxLayout(preview_box)
    self.collect_progress_bar = QProgressBar()
    self.collect_progress_bar.setRange(0, 100)
    self.collect_progress_bar.setValue(0)
    self.collect_progress_label = QLabel("未开始采集")
    self.collect_progress_label.setWordWrap(True)
    self.log_output = QTextEdit()
    self.log_output.setReadOnly(True)
    self.task_queue_status_filter = QComboBox()
    self.task_queue_status_filter.addItems(["全部状态", "待处理", "预估", "运行中", "已完成", "失败", "未完成"])
    self.task_queue_type_filter = QComboBox()
    self.task_queue_type_filter.addItems(["全部类型", "主页", "分页", "已选子页面", "自动子页面", "实际"])
    self.retry_incomplete_button = QPushButton("重试失败/未完成")
    self.retry_selected_queue_button = QPushButton("重试选中项")
    self.view_queue_result_button = QPushButton("查看队列结果")
    self.copy_queue_error_button = QPushButton("复制错误")
    self.failure_recovery_label = QLabel("失败自恢复：暂无失败项")
    self.failure_recovery_label.setWordWrap(True)
    self.enable_browser_recovery_button = QPushButton("启用真实浏览器")
    self.slow_down_recovery_button = QPushButton("调低速度")
    self.task_queue_status_filter.currentIndexChanged.connect(self.apply_task_queue_filters)
    self.task_queue_type_filter.currentIndexChanged.connect(self.apply_task_queue_filters)
    self.retry_incomplete_button.clicked.connect(self.retry_incomplete_queue_items)
    self.retry_selected_queue_button.clicked.connect(self.retry_selected_queue_item)
    self.view_queue_result_button.clicked.connect(self.view_selected_queue_result)
    self.copy_queue_error_button.clicked.connect(self.copy_selected_queue_error)
    self.enable_browser_recovery_button.clicked.connect(self.enable_browser_recovery)
    self.slow_down_recovery_button.clicked.connect(self.slow_down_recovery)
    self.task_queue_table = QTableWidget(0, 8)
    self.task_queue_table.setHorizontalHeaderLabels(["状态", "类型", "阶段", "网址", "结果数", "错误类型", "建议", "错误"])
    self.task_queue_table.verticalHeader().setVisible(False)
    self.task_queue_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    self.task_queue_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
    self.task_queue_table.itemSelectionChanged.connect(self.update_queue_detail_panel)
    self.task_queue_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
    self.task_queue_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
    self.task_queue_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
    self.task_queue_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
    self.task_queue_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
    self.task_queue_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
    self.task_queue_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
    self.task_queue_table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
    self.queue_summary_label = QLabel("队列：0 项")
    self.queue_summary_label.setWordWrap(True)
    self.queue_detail_title_label = QLabel("未选择队列项")
    self.queue_detail_title_label.setWordWrap(True)
    self.queue_detail_output = QPlainTextEdit()
    self.queue_detail_output.setReadOnly(True)
    self.queue_detail_output.setMaximumHeight(110)
    self.risk_table = QTableWidget(0, 5)
    self.risk_table.setHorizontalHeaderLabels(["级别", "检查项", "说明", "建议", "参考"])
    self.risk_table.verticalHeader().setVisible(False)
    self.risk_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
    self.risk_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
    self.risk_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
    self.risk_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
    self.risk_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
    self.risk_summary_label = QLabel("风险摘要：等待抓取前检查")
    self.risk_summary_label.setWordWrap(True)
    preview_layout.addWidget(self.collect_progress_label)
    preview_layout.addWidget(self.collect_progress_bar)
    preview_layout.addWidget(QLabel("任务预估 / 运行队列"))
    queue_filter_layout = QHBoxLayout()
    queue_filter_layout.addWidget(QLabel("状态"))
    queue_filter_layout.addWidget(self.task_queue_status_filter)
    queue_filter_layout.addWidget(QLabel("类型"))
    queue_filter_layout.addWidget(self.task_queue_type_filter)
    queue_filter_layout.addWidget(self.retry_incomplete_button)
    queue_filter_layout.addWidget(self.retry_selected_queue_button)
    queue_filter_layout.addWidget(self.view_queue_result_button)
    queue_filter_layout.addWidget(self.copy_queue_error_button)
    queue_filter_layout.addWidget(self.enable_browser_recovery_button)
    queue_filter_layout.addWidget(self.slow_down_recovery_button)
    queue_filter_layout.addStretch(1)
    preview_layout.addLayout(queue_filter_layout)
    preview_layout.addWidget(self.failure_recovery_label)
    preview_layout.addWidget(self.queue_summary_label)
    preview_layout.addWidget(self.task_queue_table)
    preview_layout.addWidget(self.queue_detail_title_label)
    preview_layout.addWidget(self.queue_detail_output)
    preview_layout.addWidget(self.log_output)
    preview_layout.addWidget(QLabel("抓取前风险/合规检查"))
    preview_layout.addWidget(self.risk_summary_label)
    preview_layout.addWidget(self.risk_table)

    top_splitter.addWidget(task_box)
    top_splitter.addWidget(preview_box)
    top_splitter.setStretchFactor(0, 2)
    top_splitter.setStretchFactor(1, 1)
    layout.addWidget(top_splitter)

    result_box = QGroupBox("本次采集结果")
    result_layout = QVBoxLayout(result_box)
    result_buttons = QHBoxLayout()
    self.export_button = QPushButton("导出结果")
    self.copy_sheets_button = QPushButton("复制到 Sheets")
    self.open_link_button = QPushButton("打开选中链接")
    self.clear_current_button = QPushButton("清空本次结果")
    self.export_button.clicked.connect(self.export_current_results)
    self.copy_sheets_button.clicked.connect(self.copy_current_results_to_sheets)
    self.open_link_button.clicked.connect(self.open_selected_url)
    self.clear_current_button.clicked.connect(self.clear_current_results)
    result_buttons.addWidget(self.export_button)
    result_buttons.addWidget(self.copy_sheets_button)
    result_buttons.addWidget(self.open_link_button)
    result_buttons.addWidget(self.clear_current_button)
    result_buttons.addStretch(1)
    self.result_status_label = QLabel("结果状态：等待采集")
    self.result_status_label.setWordWrap(True)
    self.result_export_hint_label = QLabel("导出引导：采到结果后可导出 Excel 或复制到 Sheets")
    self.result_export_hint_label.setWordWrap(True)
    self.result_table = self.create_result_table()
    self.result_table.itemSelectionChanged.connect(self.update_current_detail)
    result_splitter = QSplitter(Qt.Orientation.Horizontal)
    result_splitter.addWidget(self.result_table)
    result_splitter.addWidget(self.build_detail_panel())
    result_splitter.setStretchFactor(0, 3)
    result_splitter.setStretchFactor(1, 2)
    result_layout.addLayout(result_buttons)
    result_layout.addWidget(self.result_status_label)
    result_layout.addWidget(self.result_export_hint_label)
    result_layout.addWidget(result_splitter)
    layout.addWidget(result_box, 2)

    return page
