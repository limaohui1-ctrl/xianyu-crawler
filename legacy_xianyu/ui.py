import ctypes

from .app_core import *
from .process_tools import (
    APP_WAKE_EVENT_NAME,
    is_owned_debug_chrome,
    monitor_processes,
    terminate_owned_chrome,
    terminate_process,
)

from .worker import XianyuMonitorWorker


class WakeEventPoller(QObject):
    wake_requested = pyqtSignal()

    def __init__(self, event_name, parent=None):
        super().__init__(parent)
        self.event_name = event_name
        self.handle = None
        self.kernel32 = None
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.poll)
        self.init_event()

    def init_event(self):
        if os.name != "nt":
            return
        try:
            self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            self.kernel32.CreateEventW.argtypes = [
                ctypes.c_void_p,
                ctypes.c_bool,
                ctypes.c_bool,
                ctypes.c_wchar_p,
            ]
            self.kernel32.CreateEventW.restype = ctypes.c_void_p
            self.kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
            self.kernel32.WaitForSingleObject.restype = ctypes.c_uint32
            self.kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
            self.kernel32.CloseHandle.restype = ctypes.c_bool
            self.handle = self.kernel32.CreateEventW(None, False, False, self.event_name)
        except Exception:
            self.handle = None
            self.kernel32 = None

    def start(self):
        if self.handle and self.kernel32:
            self.timer.start()

    def poll(self):
        if not self.handle or not self.kernel32:
            return
        wait_object_0 = 0x00000000
        result = self.kernel32.WaitForSingleObject(self.handle, 0)
        if result == wait_object_0:
            self.wake_requested.emit()

    def close(self):
        self.timer.stop()
        if self.handle and self.kernel32:
            self.kernel32.CloseHandle(self.handle)
        self.handle = None
        self.kernel32 = None


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"闲鱼多商品监测 - {APP_VERSION}")
        self.resize(1220, 780)
        self.worker_thread = None
        self.worker = None
        self.found_items = []
        self.comparison_items = []
        self.price_suggestion_items = []
        self.tray_icon = None
        self.force_exit = False
        self.tray_notice_shown = False
        self.settings_loaded = False
        self.suspend_settings_save = True
        self.log_noise_buffer = {}
        self.owned_chrome_pid = None
        self.cdp_port = None
        self.cdp_endpoint = None
        self.log_write_failed = False
        self.active_result_group_filter = None
        self.settings_save_timer = QTimer(self)
        self.settings_save_timer.setSingleShot(True)
        self.settings_save_timer.timeout.connect(self.save_current_settings)
        self.log_summary_timer = QTimer(self)
        self.log_summary_timer.setInterval(2500)
        self.log_summary_timer.timeout.connect(self.flush_log_noise_summary)
        self.smart_rules = load_smart_rules()
        self.item_statuses = load_item_statuses()
        self._build_ui()
        self.load_saved_settings()
        for warning in take_corrupt_json_warnings():
            self.append_log(f"[数据保护] {warning}")
        self.setup_settings_autosave()
        self.suspend_settings_save = False
        self.load_saved_hits()
        self.setup_tray_icon()
        self.setup_wake_event()

    def _build_ui(self):
        root = QWidget()
        layout = QVBoxLayout(root)

        config_box = QGroupBox("监测配置")
        grid = QGridLayout(config_box)

        self.config_table = QTableWidget(0, 4)
        self.config_table.setHorizontalHeaderLabels(["关键词", "最低价", "最高价", "扫描页数"])
        self.config_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.config_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        self.config_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        self.config_table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.ResizeToContents
        )
        self.config_table.verticalHeader().setVisible(False)
        self.add_monitor_row("Mac mini M4", 2500, 3500, 1)
        self.add_monitor_row("Xeon E5 2696 V4", 100, 200, 1)

        self.interval_min_input = QSpinBox()
        self.interval_min_input.setRange(10, 86400)
        self.interval_min_input.setValue(180)
        self.interval_max_input = QSpinBox()
        self.interval_max_input.setRange(10, 86400)
        self.interval_max_input.setValue(300)
        self.smart_filter_checkbox = QCheckBox("启用智能过滤")
        self.smart_filter_checkbox.setChecked(True)
        self.smart_match_checkbox = QCheckBox("智能匹配关键词规格")
        self.smart_match_checkbox.setChecked(True)
        self.personal_filter_checkbox = QCheckBox("优先个人闲置")
        self.personal_filter_checkbox.setChecked(True)
        self.platform_xianyu_checkbox = QCheckBox("闲鱼")
        self.platform_xianyu_checkbox.setChecked(True)
        self.platform_jd_checkbox = QCheckBox("京东")
        self.platform_jd_checkbox.setToolTip(
            "京东容易触发登录/验证；账号提示风险时建议先关闭。"
            "软件检测到验证页会自动暂停京东扫描。"
        )
        self.platform_taobao_checkbox = QCheckBox("淘宝")
        self.platform_taobao_checkbox.setToolTip(
            "淘宝遇到登录/验证页时会自动暂停本平台扫描，降低反复触发风险。"
        )
        self.min_alert_score_input = QSpinBox()
        self.min_alert_score_input.setRange(0, 100)
        self.min_alert_score_input.setValue(55)
        self.min_alert_score_input.setSuffix(" 分")
        self.black_words_input = QLineEdit()
        self.black_words_input.setPlaceholderText("可选：额外排除词，用逗号分隔")

        config_button_row = QHBoxLayout()
        self.add_config_button = QPushButton("添加商品")
        self.remove_config_button = QPushButton("删除选中商品")
        self.add_config_button.clicked.connect(self.add_empty_monitor_row)
        self.remove_config_button.clicked.connect(self.remove_selected_monitor_rows)
        config_button_row.addWidget(self.add_config_button)
        config_button_row.addWidget(self.remove_config_button)
        config_button_row.addStretch(1)

        grid.addWidget(self.config_table, 0, 0, 1, 4)
        grid.addLayout(config_button_row, 1, 0, 1, 4)
        grid.addWidget(QLabel("最短间隔秒"), 2, 0)
        grid.addWidget(self.interval_min_input, 2, 1)
        grid.addWidget(QLabel("最长间隔秒"), 2, 2)
        grid.addWidget(self.interval_max_input, 2, 3)
        grid.addWidget(QLabel("过滤"), 3, 0)
        grid.addWidget(self.smart_filter_checkbox, 3, 1)
        grid.addWidget(self.smart_match_checkbox, 3, 2)
        grid.addWidget(self.personal_filter_checkbox, 3, 3)
        grid.addWidget(QLabel("最低提醒评分"), 4, 0)
        grid.addWidget(self.min_alert_score_input, 4, 1)
        grid.addWidget(QLabel("额外排除词"), 5, 0)
        grid.addWidget(self.black_words_input, 5, 1, 1, 3)
        grid.addWidget(QLabel("监测平台"), 6, 0)
        grid.addWidget(self.platform_xianyu_checkbox, 6, 1)
        grid.addWidget(self.platform_jd_checkbox, 6, 2)
        grid.addWidget(self.platform_taobao_checkbox, 6, 3)

        rule_box = QGroupBox("规则中心")
        rule_grid = QGridLayout(rule_box)
        self.filter_accessories_checkbox = QCheckBox("过滤配件")
        self.filter_empty_boxes_checkbox = QCheckBox("过滤空盒")
        self.filter_services_checkbox = QCheckBox("过滤服务/虚拟内容")
        self.filter_bundles_checkbox = QCheckBox("过滤套装打包")
        self.merchant_penalty_checkbox = QCheckBox("商家模板降权")
        for checkbox in (
            self.filter_accessories_checkbox,
            self.filter_empty_boxes_checkbox,
            self.filter_services_checkbox,
            self.filter_bundles_checkbox,
            self.merchant_penalty_checkbox,
        ):
            checkbox.setChecked(True)

        self.export_log_button = QPushButton("导出重要诊断")
        self.export_full_log_button = QPushButton("导出完整日志")
        self.export_log_button.clicked.connect(self.export_diagnostic_log)
        self.export_full_log_button.clicked.connect(self.export_full_diagnostic_log)
        self.clear_cache_button = QPushButton("清理浏览器缓存")
        self.clear_cache_button.clicked.connect(self.clear_chrome_cache)
        rule_grid.addWidget(self.filter_accessories_checkbox, 0, 0)
        rule_grid.addWidget(self.filter_empty_boxes_checkbox, 0, 1)
        rule_grid.addWidget(self.filter_services_checkbox, 0, 2)
        rule_grid.addWidget(self.filter_bundles_checkbox, 1, 0)
        rule_grid.addWidget(self.merchant_penalty_checkbox, 1, 1)
        rule_grid.addWidget(self.export_log_button, 1, 2)
        rule_grid.addWidget(self.export_full_log_button, 2, 1)
        rule_grid.addWidget(self.clear_cache_button, 2, 0)

        environment_box = QGroupBox("环境守护")
        environment_grid = QGridLayout(environment_box)
        self.environment_status_label = QLabel("尚未检查")
        self.process_status_label = QLabel("尚未检查")
        self.check_environment_button = QPushButton("检查环境")
        self.launch_chrome_button = QPushButton("一键启动 Chrome")
        self.refresh_process_button = QPushButton("刷新后台进程")
        self.stop_other_processes_button = QPushButton("结束其他实例")
        self.check_environment_button.clicked.connect(self.check_environment)
        self.launch_chrome_button.clicked.connect(self.launch_chrome_debug_browser)
        self.refresh_process_button.clicked.connect(self.refresh_process_status)
        self.stop_other_processes_button.clicked.connect(self.stop_other_instances)
        environment_grid.addWidget(QLabel("当前状态"), 0, 0)
        environment_grid.addWidget(self.environment_status_label, 0, 1, 1, 2)
        environment_grid.addWidget(QLabel("后台进程"), 1, 0)
        environment_grid.addWidget(self.process_status_label, 1, 1, 1, 2)
        environment_grid.addWidget(self.check_environment_button, 2, 0)
        environment_grid.addWidget(self.launch_chrome_button, 2, 1)
        environment_grid.addWidget(self.refresh_process_button, 3, 0)
        environment_grid.addWidget(self.stop_other_processes_button, 3, 1)
        environment_grid.setColumnStretch(2, 1)

        button_row = QHBoxLayout()
        self.start_button = QPushButton("开始监测")
        self.stop_button = QPushButton("停止监测")
        self.stop_button.setEnabled(False)
        self.start_button.clicked.connect(self.start_monitoring)
        self.stop_button.clicked.connect(self.stop_monitoring)
        button_row.addWidget(self.start_button)
        button_row.addWidget(self.stop_button)

        result_box = QGroupBox("命中结果")
        result_layout = QVBoxLayout(result_box)
        self.result_table = QTableWidget(0, 11)
        self.result_table.setHorizontalHeaderLabels(
            ["时间", "状态", "平台", "关键词", "页码", "价格", "评分", "等级", "理由", "标题", "链接"]
        )
        self.result_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self.result_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        self.result_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        self.result_table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.ResizeToContents
        )
        self.result_table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeMode.ResizeToContents
        )
        self.result_table.horizontalHeader().setSectionResizeMode(
            5, QHeaderView.ResizeMode.ResizeToContents
        )
        self.result_table.horizontalHeader().setSectionResizeMode(
            6, QHeaderView.ResizeMode.ResizeToContents
        )
        self.result_table.horizontalHeader().setSectionResizeMode(
            7, QHeaderView.ResizeMode.ResizeToContents
        )
        self.result_table.horizontalHeader().setSectionResizeMode(
            8, QHeaderView.ResizeMode.Stretch
        )
        self.result_table.horizontalHeader().setSectionResizeMode(
            9, QHeaderView.ResizeMode.Stretch
        )
        self.result_table.horizontalHeader().setSectionResizeMode(
            10, QHeaderView.ResizeMode.ResizeToContents
        )
        self.result_table.verticalHeader().setVisible(False)
        self.result_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.result_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.result_table.setWordWrap(False)
        self.result_table.cellDoubleClicked.connect(self.open_result_link_at_row)
        self.result_table.itemSelectionChanged.connect(self.update_result_detail_from_selection)

        result_filter_row = QHBoxLayout()
        self.result_search_input = QLineEdit()
        self.result_search_input.setPlaceholderText("搜索标题、关键词、平台或链接")
        self.result_status_filter = QComboBox()
        self.result_status_filter.addItems(["全部状态"] + HIT_STATUS_OPTIONS)
        self.result_platform_filter = QComboBox()
        self.result_platform_filter.addItems(["全部平台", "闲鱼", "京东", "淘宝"])
        self.result_sort_combo = QComboBox()
        self.result_sort_combo.addItems(
            [
                "按时间最新",
                "按价格最低",
                "按价格最高",
                "按评分最高",
                "按平台",
                "按状态",
            ]
        )
        self.only_favorites_button = QPushButton("只看收藏")
        self.only_favorites_button.setCheckable(True)
        self.result_filter_label = QLabel("显示全部结果")
        self.result_filter_label.setObjectName("subtleLabel")
        self.result_search_input.textChanged.connect(self.apply_result_filter)
        self.result_status_filter.currentTextChanged.connect(self.apply_result_filter)
        self.result_platform_filter.currentTextChanged.connect(self.apply_result_filter)
        self.result_sort_combo.currentTextChanged.connect(self.apply_result_sort_and_filter)
        self.only_favorites_button.toggled.connect(self.toggle_only_favorites)
        self.clear_result_filters_button = QPushButton("清除筛选")
        self.clear_result_filters_button.clicked.connect(self.clear_result_filters)
        result_filter_row.addWidget(QLabel("结果搜索"))
        result_filter_row.addWidget(self.result_search_input, 1)
        result_filter_row.addWidget(self.result_status_filter)
        result_filter_row.addWidget(self.result_platform_filter)
        result_filter_row.addWidget(self.result_sort_combo)
        result_filter_row.addWidget(self.only_favorites_button)
        result_filter_row.addWidget(self.clear_result_filters_button)
        result_filter_row.addWidget(self.result_filter_label)

        result_status_button_row = QHBoxLayout()
        result_manage_button_row = QHBoxLayout()
        self.open_link_button = QPushButton("打开商品链接")
        self.mark_viewed_button = QPushButton("标记已查看")
        self.mark_contacted_button = QPushButton("标记已联系")
        self.mark_ignored_button = QPushButton("标记忽略")
        self.mark_favorite_button = QPushButton("收藏")
        self.mark_bad_button = QPushButton("标记误报")
        self.mark_good_button = QPushButton("标记好货")
        self.clear_smart_rules_button = QPushButton("清空学习规则")
        self.export_results_button = QPushButton("导出结果")
        self.clear_results_button = QPushButton("清空结果")
        self.clear_database_button = QPushButton("清空去重记录")
        self.batch_viewed_button = QPushButton("可见标已查看")
        self.batch_favorite_button = QPushButton("可见标收藏")
        self.batch_ignored_button = QPushButton("可见标忽略")
        self.detail_open_link_button = QPushButton("打开链接")
        self.detail_viewed_button = QPushButton("已查看")
        self.detail_contacted_button = QPushButton("已联系")
        self.detail_favorite_button = QPushButton("收藏")
        self.detail_ignored_button = QPushButton("忽略")
        self.open_link_button.clicked.connect(self.open_selected_result_link)
        self.mark_viewed_button.clicked.connect(self.mark_selected_result_viewed)
        self.mark_contacted_button.clicked.connect(self.mark_selected_result_contacted)
        self.mark_ignored_button.clicked.connect(self.mark_selected_result_ignored)
        self.mark_favorite_button.clicked.connect(self.mark_selected_result_favorite)
        self.mark_bad_button.clicked.connect(self.mark_selected_result_bad)
        self.mark_good_button.clicked.connect(self.mark_selected_result_good)
        self.clear_smart_rules_button.clicked.connect(self.clear_smart_rules)
        self.export_results_button.clicked.connect(self.export_results)
        self.clear_results_button.clicked.connect(self.clear_results)
        self.clear_database_button.clicked.connect(self.clear_database)
        self.batch_viewed_button.clicked.connect(lambda: self.batch_set_visible_status("已查看"))
        self.batch_favorite_button.clicked.connect(lambda: self.batch_set_visible_status("收藏"))
        self.batch_ignored_button.clicked.connect(lambda: self.batch_set_visible_status("忽略"))
        self.detail_open_link_button.clicked.connect(self.open_selected_result_link)
        self.detail_viewed_button.clicked.connect(self.mark_selected_result_viewed)
        self.detail_contacted_button.clicked.connect(self.mark_selected_result_contacted)
        self.detail_favorite_button.clicked.connect(self.mark_selected_result_favorite)
        self.detail_ignored_button.clicked.connect(self.mark_selected_result_ignored)
        result_status_button_row.addWidget(self.open_link_button)
        result_status_button_row.addWidget(self.mark_viewed_button)
        result_status_button_row.addWidget(self.mark_contacted_button)
        result_status_button_row.addWidget(self.mark_ignored_button)
        result_status_button_row.addWidget(self.mark_favorite_button)
        result_status_button_row.addStretch(1)
        result_manage_button_row.addWidget(self.mark_bad_button)
        result_manage_button_row.addWidget(self.mark_good_button)
        result_manage_button_row.addWidget(self.clear_smart_rules_button)
        result_manage_button_row.addWidget(self.export_results_button)
        result_manage_button_row.addWidget(self.clear_results_button)
        result_manage_button_row.addWidget(self.clear_database_button)
        result_manage_button_row.addStretch(1)

        result_batch_button_row = QHBoxLayout()
        result_batch_button_row.addWidget(self.batch_viewed_button)
        result_batch_button_row.addWidget(self.batch_favorite_button)
        result_batch_button_row.addWidget(self.batch_ignored_button)
        result_batch_button_row.addStretch(1)

        self.result_group_box = QGroupBox("结果分组")
        result_group_layout = QVBoxLayout(self.result_group_box)
        result_group_toolbar = QHBoxLayout()
        self.result_group_type_combo = QComboBox()
        self.result_group_type_combo.addItems(["按关键词", "按平台", "按状态"])
        self.result_group_hint_label = QLabel("双击分组可快速筛选")
        self.result_group_hint_label.setObjectName("subtleLabel")
        self.result_group_type_combo.currentTextChanged.connect(self.on_result_group_type_changed)
        result_group_toolbar.addWidget(QLabel("分组方式"))
        result_group_toolbar.addWidget(self.result_group_type_combo)
        result_group_toolbar.addWidget(self.result_group_hint_label, 1)
        self.result_group_table = QTableWidget(0, 6)
        self.result_group_table.setHorizontalHeaderLabels(
            ["分组", "总数", "未处理", "收藏", "最低价", "最高评分"]
        )
        for column in range(6):
            self.result_group_table.horizontalHeader().setSectionResizeMode(
                column,
                QHeaderView.ResizeMode.ResizeToContents,
            )
        self.result_group_table.horizontalHeader().setStretchLastSection(True)
        self.result_group_table.verticalHeader().setVisible(False)
        self.result_group_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.result_group_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.result_group_table.cellDoubleClicked.connect(self.apply_result_group_filter)
        result_group_layout.addLayout(result_group_toolbar)
        result_group_layout.addWidget(self.result_group_table)

        self.result_detail_box = QGroupBox("结果详情")
        result_detail_layout = QVBoxLayout(self.result_detail_box)
        self.result_detail_summary_label = QLabel("选中一条命中结果后，这里显示完整信息。")
        self.result_detail_summary_label.setObjectName("detailSummary")
        self.result_detail_title_label = QLabel("标题：-")
        self.result_detail_reason_label = QLabel("理由：-")
        self.result_detail_url_label = QLabel("链接：-")
        self.result_detail_url_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self.result_detail_status_label = QLabel("状态：-")
        for detail_label in (
            self.result_detail_summary_label,
            self.result_detail_title_label,
            self.result_detail_reason_label,
            self.result_detail_url_label,
            self.result_detail_status_label,
        ):
            detail_label.setWordWrap(True)
            detail_label.setMinimumWidth(0)
        detail_button_row = QHBoxLayout()
        detail_button_row.addWidget(self.detail_open_link_button)
        detail_button_row.addWidget(self.detail_viewed_button)
        detail_button_row.addWidget(self.detail_contacted_button)
        detail_button_row.addWidget(self.detail_favorite_button)
        detail_button_row.addWidget(self.detail_ignored_button)
        detail_button_row.addStretch(1)
        result_detail_layout.addWidget(self.result_detail_summary_label)
        result_detail_layout.addWidget(self.result_detail_title_label)
        result_detail_layout.addWidget(self.result_detail_reason_label)
        result_detail_layout.addWidget(self.result_detail_status_label)
        result_detail_layout.addWidget(self.result_detail_url_label)
        result_detail_layout.addLayout(detail_button_row)
        result_detail_layout.addStretch(1)

        self.result_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.result_splitter.addWidget(self.result_table)
        self.result_splitter.addWidget(self.result_detail_box)
        self.result_splitter.setSizes([760, 320])
        self.result_splitter.setStretchFactor(0, 1)
        self.result_splitter.setStretchFactor(1, 0)
        self.result_splitter.setCollapsible(0, False)
        self.result_splitter.setCollapsible(1, False)

        result_action_panel = QWidget()
        result_action_panel_layout = QVBoxLayout(result_action_panel)
        result_action_panel_layout.setContentsMargins(8, 8, 8, 8)
        result_action_panel_layout.addLayout(result_status_button_row)
        result_action_panel_layout.addLayout(result_manage_button_row)

        result_batch_panel = QWidget()
        result_batch_panel_layout = QVBoxLayout(result_batch_panel)
        result_batch_panel_layout.setContentsMargins(8, 8, 8, 8)
        batch_hint = QLabel("批量操作只处理当前筛选后可见的结果。")
        batch_hint.setObjectName("subtleLabel")
        batch_hint.setWordWrap(True)
        result_batch_panel_layout.addWidget(batch_hint)
        result_batch_panel_layout.addLayout(result_batch_button_row)
        result_batch_panel_layout.addStretch(1)

        self.result_toolbox = QToolBox()
        self.result_toolbox.addItem(self.result_detail_box, "详情")
        self.result_toolbox.addItem(self.result_group_box, "分组")
        self.result_toolbox.addItem(result_action_panel, "操作")
        self.result_toolbox.addItem(result_batch_panel, "批量")
        self.result_toolbox.setCurrentIndex(0)

        result_layout.addLayout(result_filter_row)
        result_layout.addWidget(self.result_splitter, 1)
        result_layout.addWidget(self.result_toolbox)

        comparison_box = QGroupBox("平台比价")
        comparison_layout = QVBoxLayout(comparison_box)
        self.comparison_table = QTableWidget(0, 7)
        self.comparison_table.setHorizontalHeaderLabels(
            ["时间", "关键词", "闲鱼最低", "京东最低", "淘宝最低", "最优平台", "最优链接"]
        )
        for column in range(6):
            self.comparison_table.horizontalHeader().setSectionResizeMode(
                column,
                QHeaderView.ResizeMode.ResizeToContents,
            )
        self.comparison_table.horizontalHeader().setSectionResizeMode(
            6,
            QHeaderView.ResizeMode.Stretch,
        )
        self.comparison_table.verticalHeader().setVisible(False)
        self.comparison_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.comparison_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.comparison_table.cellDoubleClicked.connect(self.open_comparison_link_at_row)
        comparison_layout.addWidget(self.comparison_table)

        price_suggestion_box = QGroupBox("智能价格建议")
        price_suggestion_layout = QVBoxLayout(price_suggestion_box)
        self.price_suggestion_table = QTableWidget(0, 6)
        self.price_suggestion_table.setHorizontalHeaderLabels(
            ["时间", "关键词", "平台最低", "当前区间", "建议区间", "理由"]
        )
        for column in range(5):
            self.price_suggestion_table.horizontalHeader().setSectionResizeMode(
                column,
                QHeaderView.ResizeMode.ResizeToContents,
            )
        self.price_suggestion_table.horizontalHeader().setSectionResizeMode(
            5,
            QHeaderView.ResizeMode.Stretch,
        )
        self.price_suggestion_table.verticalHeader().setVisible(False)
        self.price_suggestion_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.price_suggestion_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )

        price_suggestion_button_row = QHBoxLayout()
        self.apply_price_suggestion_button = QPushButton("应用选中建议")
        self.apply_latest_price_suggestion_button = QPushButton("一键应用最新建议")
        self.ignore_price_suggestion_button = QPushButton("忽略选中建议")
        self.apply_price_suggestion_button.clicked.connect(self.apply_selected_price_suggestion)
        self.apply_latest_price_suggestion_button.clicked.connect(self.apply_latest_price_suggestion)
        self.ignore_price_suggestion_button.clicked.connect(self.ignore_selected_price_suggestion)
        self.apply_latest_price_suggestion_button.setObjectName("primaryButton")
        price_suggestion_button_row.addWidget(self.apply_price_suggestion_button)
        price_suggestion_button_row.addWidget(self.apply_latest_price_suggestion_button)
        price_suggestion_button_row.addWidget(self.ignore_price_suggestion_button)
        price_suggestion_button_row.addStretch(1)
        price_suggestion_layout.addWidget(self.price_suggestion_table)
        price_suggestion_layout.addLayout(price_suggestion_button_row)

        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.important_log_output = QTextEdit()
        self.important_log_output.setReadOnly(True)
        self.important_log_output.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)

        self.apply_app_style()

        header_frame = QFrame()
        header_frame.setObjectName("headerFrame")
        header_layout = QHBoxLayout(header_frame)
        title_label = QLabel(f"闲鱼监测控制台  {APP_VERSION}")
        title_label.setObjectName("appTitle")
        title_label.setMinimumWidth(0)
        self.header_status_label = QLabel("待机")
        self.header_status_label.setObjectName("statusPill")
        self.header_status_label.setMinimumWidth(0)
        self.header_status_label.setStyleSheet(
            "background: #e6f4ea; color: #166534; border-radius: 4px; padding: 5px 10px;"
        )
        header_layout.addWidget(title_label)
        header_layout.addStretch(1)
        header_layout.addWidget(self.header_status_label)

        button_frame = QFrame()
        button_frame.setObjectName("controlFrame")
        button_frame_layout = QVBoxLayout(button_frame)
        button_frame_layout.addLayout(button_row)

        self.dashboard_hit_count_label = QLabel("0")
        self.dashboard_pending_count_label = QLabel("0")
        self.dashboard_favorite_count_label = QLabel("0")
        self.dashboard_price_suggestion_count_label = QLabel("0")
        self.dashboard_task_count_label = QLabel("0")
        self.dashboard_env_label = QLabel("尚未检查")
        self.dashboard_check_environment_button = QPushButton("检查环境")
        self.dashboard_launch_chrome_button = QPushButton("启动 Chrome")
        self.dashboard_open_results_button = QPushButton("查看命中结果")
        self.dashboard_check_environment_button.clicked.connect(self.check_environment)
        self.dashboard_launch_chrome_button.clicked.connect(self.launch_chrome_debug_browser)
        self.dashboard_open_results_button.clicked.connect(lambda: self.nav_list.setCurrentRow(2))

        dashboard_page = QWidget()
        dashboard_layout = QVBoxLayout(dashboard_page)
        dashboard_layout.setContentsMargins(0, 0, 0, 0)
        dashboard_layout.setSpacing(12)
        metric_grid = QGridLayout()
        metric_grid.setSpacing(10)
        metric_grid.addWidget(self.make_metric_card("命中总数", self.dashboard_hit_count_label), 0, 0)
        metric_grid.addWidget(self.make_metric_card("待处理", self.dashboard_pending_count_label), 0, 1)
        metric_grid.addWidget(self.make_metric_card("收藏", self.dashboard_favorite_count_label), 0, 2)
        metric_grid.addWidget(self.make_metric_card("价格建议", self.dashboard_price_suggestion_count_label), 0, 3)
        metric_grid.addWidget(self.make_metric_card("监测任务", self.dashboard_task_count_label), 1, 0)
        metric_grid.addWidget(self.make_metric_card("浏览器环境", self.dashboard_env_label), 1, 1, 1, 3)
        dashboard_layout.addLayout(metric_grid)
        dashboard_layout.addWidget(button_frame)
        dashboard_shortcut_row = QHBoxLayout()
        dashboard_shortcut_row.addWidget(self.dashboard_check_environment_button)
        dashboard_shortcut_row.addWidget(self.dashboard_launch_chrome_button)
        dashboard_shortcut_row.addWidget(self.dashboard_open_results_button)
        dashboard_shortcut_row.addStretch(1)
        dashboard_layout.addLayout(dashboard_shortcut_row)
        dashboard_layout.addStretch(1)

        task_page = QWidget()
        task_layout = QVBoxLayout(task_page)
        task_layout.setContentsMargins(0, 0, 0, 0)
        task_layout.setSpacing(12)
        task_layout.addWidget(config_box)
        task_layout.addWidget(rule_box)
        task_layout.addStretch(1)

        result_page = QWidget()
        result_page_layout = QVBoxLayout(result_page)
        result_page_layout.setContentsMargins(0, 0, 0, 0)
        result_page_layout.setSpacing(10)
        result_page_layout.addWidget(result_box)

        price_page = QWidget()
        price_page_layout = QVBoxLayout(price_page)
        price_page_layout.setContentsMargins(0, 0, 0, 0)
        price_page_layout.setSpacing(10)
        price_page_layout.addWidget(comparison_box, 1)
        price_page_layout.addWidget(price_suggestion_box, 1)

        environment_page = QWidget()
        environment_layout = QVBoxLayout(environment_page)
        environment_layout.setContentsMargins(0, 0, 0, 0)
        environment_layout.setSpacing(12)
        environment_layout.addWidget(environment_box)
        environment_layout.addStretch(1)

        self.sidebar_scroll = QScrollArea()
        self.sidebar_scroll.setWidgetResizable(True)
        self.sidebar_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.nav_list = QListWidget()
        self.nav_list.setObjectName("navList")
        for title in ("控制台", "监测任务", "命中结果", "价格分析", "浏览器环境", "日志诊断"):
            self.nav_list.addItem(QListWidgetItem(title))
        self.nav_list.setCurrentRow(0)
        self.sidebar_scroll.setWidget(self.nav_list)
        self.sidebar_scroll.setMinimumWidth(176)
        self.sidebar_scroll.setMaximumWidth(210)
        self.sidebar_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        log_page = QWidget()
        log_layout = QVBoxLayout(log_page)
        log_layout.setContentsMargins(0, 0, 0, 0)
        self.log_tabs = QTabWidget()
        self.log_tabs.addTab(self.important_log_output, "重要日志")
        self.log_tabs.addTab(self.log_output, "完整日志")
        log_layout.addWidget(self.log_tabs)

        self.workspace_stack = QStackedWidget()
        self.workspace_stack.addWidget(dashboard_page)
        self.workspace_stack.addWidget(task_page)
        self.workspace_stack.addWidget(result_page)
        self.workspace_stack.addWidget(price_page)
        self.workspace_stack.addWidget(environment_page)
        self.workspace_stack.addWidget(log_page)
        self.workspace_tabs = self.workspace_stack
        self.nav_list.currentRowChanged.connect(self.workspace_stack.setCurrentIndex)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.sidebar_scroll)
        splitter.addWidget(self.workspace_stack)
        splitter.setSizes([188, 1032])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)

        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        layout.addWidget(header_frame)
        layout.addWidget(splitter, 1)
        self.setCentralWidget(root)
        self.apply_responsive_layout_defaults()
        self.refresh_process_status()
        self.refresh_dashboard_summary()

    def apply_app_style(self):
        self.setStyleSheet(
            """
            QMainWindow, QWidget {
                background: #f5f7fa;
                color: #17212b;
                font-size: 13px;
            }
            QFrame#headerFrame, QFrame#controlFrame, QFrame#metricCard {
                background: #ffffff;
                border: 1px solid #d8e0e8;
                border-radius: 6px;
            }
            QLabel#appTitle {
                font-size: 20px;
                font-weight: 700;
                color: #102033;
            }
            QLabel#metricValue {
                font-size: 26px;
                font-weight: 700;
                color: #0f4c75;
                background: transparent;
            }
            QLabel#metricTitle, QLabel#subtleLabel {
                color: #607080;
                font-weight: 400;
                background: transparent;
            }
            QLabel#detailSummary {
                color: #102a43;
                font-size: 14px;
                font-weight: 700;
            }
            QListWidget#navList {
                background: #ffffff;
                border: 1px solid #d8e0e8;
                border-radius: 6px;
                padding: 8px;
                outline: 0;
            }
            QListWidget#navList::item {
                min-height: 38px;
                padding: 0 12px;
                border-radius: 5px;
                color: #27384a;
            }
            QListWidget#navList::item:selected {
                background: #d9ecff;
                color: #0b4f7a;
                font-weight: 700;
            }
            QListWidget#navList::item:hover {
                background: #edf5fc;
            }
            QGroupBox {
                background: #ffffff;
                border: 1px solid #d8e0e8;
                border-radius: 6px;
                margin-top: 14px;
                padding: 12px 10px 10px 10px;
                font-weight: 600;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }
            QPushButton {
                background: #176b87;
                color: white;
                border: 0;
                border-radius: 5px;
                padding: 7px 12px;
            }
            QPushButton:hover {
                background: #1f7f9f;
            }
            QPushButton:disabled {
                background: #b6c2cf;
            }
            QLineEdit, QSpinBox, QComboBox, QTextEdit, QTableWidget {
                background: #ffffff;
                border: 1px solid #cbd6e2;
                border-radius: 4px;
                min-height: 24px;
            }
            QLineEdit, QSpinBox, QComboBox {
                padding: 3px 6px;
            }
            QTableWidget {
                gridline-color: #e6edf3;
                selection-background-color: #d7ecff;
                selection-color: #102a43;
            }
            QHeaderView::section {
                background: #edf2f7;
                border: 0;
                border-right: 1px solid #d8e0e8;
                padding: 6px;
                font-weight: 600;
            }
            QTabWidget::pane {
                border: 1px solid #d8e0e8;
                background: #ffffff;
                border-radius: 6px;
            }
            QTabBar::tab {
                background: #e7edf3;
                padding: 8px 14px;
                margin-right: 3px;
                border-top-left-radius: 5px;
                border-top-right-radius: 5px;
            }
            QTabBar::tab:selected {
                background: #ffffff;
                color: #0f4c75;
            }
            """
        )

    def make_metric_card(self, title, value_label):
        card = QFrame()
        card.setObjectName("metricCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        title_label = QLabel(title)
        title_label.setObjectName("metricTitle")
        value_label.setObjectName("metricValue")
        value_label.setMinimumWidth(0)
        value_label.setWordWrap(True)
        layout.addWidget(title_label)
        layout.addWidget(value_label)
        layout.addStretch(1)
        return card

    def refresh_dashboard_summary(self):
        if not hasattr(self, "dashboard_hit_count_label"):
            return
        total_hits = len(self.found_items)
        pending_hits = sum(
            1 for item in self.found_items if item.get("status", HIT_STATUS_DEFAULT) == HIT_STATUS_DEFAULT
        )
        favorite_hits = sum(1 for item in self.found_items if item.get("status") == "收藏")
        self.dashboard_hit_count_label.setText(str(total_hits))
        self.dashboard_pending_count_label.setText(str(pending_hits))
        self.dashboard_favorite_count_label.setText(str(favorite_hits))
        self.dashboard_price_suggestion_count_label.setText(str(len(self.price_suggestion_items)))
        self.dashboard_task_count_label.setText(str(self.config_table.rowCount()))
        self.dashboard_env_label.setText(self.environment_status_label.text())

    def apply_responsive_layout_defaults(self):
        self.setMinimumSize(760, 520)
        compact_buttons = [
            self.add_config_button,
            self.remove_config_button,
            self.export_log_button,
            self.export_full_log_button,
            self.clear_cache_button,
            self.check_environment_button,
            self.launch_chrome_button,
            self.refresh_process_button,
            self.stop_other_processes_button,
            self.start_button,
            self.stop_button,
            self.open_link_button,
            self.mark_viewed_button,
            self.mark_contacted_button,
            self.mark_ignored_button,
            self.mark_favorite_button,
            self.mark_bad_button,
            self.mark_good_button,
            self.clear_smart_rules_button,
            self.export_results_button,
            self.clear_results_button,
            self.clear_database_button,
            self.only_favorites_button,
            self.clear_result_filters_button,
            self.batch_viewed_button,
            self.batch_favorite_button,
            self.batch_ignored_button,
            self.detail_open_link_button,
            self.detail_viewed_button,
            self.detail_contacted_button,
            self.detail_favorite_button,
            self.detail_ignored_button,
            self.apply_price_suggestion_button,
            self.apply_latest_price_suggestion_button,
            self.ignore_price_suggestion_button,
            self.dashboard_check_environment_button,
            self.dashboard_launch_chrome_button,
            self.dashboard_open_results_button,
        ]
        for button in compact_buttons:
            button.setMinimumWidth(0)
            button.setToolTip(button.text())
            button.setSizePolicy(
                QSizePolicy.Policy.Minimum,
                QSizePolicy.Policy.Fixed,
            )

        for label in (
            self.environment_status_label,
            self.process_status_label,
            self.result_filter_label,
        ):
            label.setMinimumWidth(0)
            label.setWordWrap(True)

        for table in (
            self.config_table,
            self.result_table,
            self.comparison_table,
            self.price_suggestion_table,
            self.result_group_table,
        ):
            table.setMinimumWidth(0)
            table.setHorizontalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
            table.setVerticalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
            table.horizontalHeader().setMinimumSectionSize(48)

        self.config_table.setMinimumHeight(96)
        self.config_table.horizontalHeader().setStretchLastSection(True)

        result_widths = {
            0: 142,
            1: 72,
            2: 62,
            3: 96,
            4: 54,
            5: 70,
            6: 58,
            7: 58,
            8: 190,
            9: 260,
            10: 220,
        }
        for column, width in result_widths.items():
            self.result_table.horizontalHeader().setSectionResizeMode(
                column,
                QHeaderView.ResizeMode.Interactive,
            )
            self.result_table.setColumnWidth(column, width)


    def setup_tray_icon(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.append_log("[托盘] 当前系统没有可用托盘，关闭窗口会直接退出。")
            return

        app = QApplication.instance()
        icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        if app:
            app.setWindowIcon(icon)
        self.setWindowIcon(icon)

        self.tray_icon = QSystemTrayIcon(icon, self)
        self.tray_icon.setToolTip("闲鱼多商品监测")
        tray_menu = QMenu(self)
        self.show_window_action = QAction("显示窗口", self)
        self.hide_window_action = QAction("隐藏窗口", self)
        self.quit_action = QAction("真正退出", self)
        self.show_window_action.triggered.connect(self.show_from_tray)
        self.hide_window_action.triggered.connect(self.hide_to_tray)
        self.quit_action.triggered.connect(self.quit_from_tray)
        tray_menu.addAction(self.show_window_action)
        tray_menu.addAction(self.hide_window_action)
        tray_menu.addSeparator()
        tray_menu.addAction(self.quit_action)
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.on_tray_activated)
        self.tray_icon.show()
        self.append_log("[托盘] 已启用托盘图标，关闭窗口会隐藏到托盘。")

    def on_tray_activated(self, reason):
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            if self.isVisible():
                self.hide_to_tray()
            else:
                self.show_from_tray()

    def show_from_tray(self):
        self.showNormal()
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized)
        self.raise_()
        self.activateWindow()
        if os.name == "nt":
            try:
                self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
                self.show()
                self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, False)
                self.show()
                self.raise_()
                self.activateWindow()
            except Exception:
                pass

    def setup_wake_event(self):
        self.wake_event_poller = WakeEventPoller(APP_WAKE_EVENT_NAME, self)
        self.wake_event_poller.wake_requested.connect(self.show_from_existing_instance)
        self.wake_event_poller.start()

    def show_from_existing_instance(self):
        self.show_from_tray()
        self.append_log("[进程管理] 已响应启动器请求，显示现有窗口。")

    def hide_to_tray(self):
        self.hide()
        if self.tray_icon and not self.tray_notice_shown:
            self.tray_icon.showMessage(
                "闲鱼监测仍在运行",
                "窗口已隐藏到托盘。右键托盘图标可显示窗口或真正退出。",
                QSystemTrayIcon.MessageIcon.Information,
                3000,
            )
            self.tray_notice_shown = True

    def quit_from_tray(self):
        self.force_exit = True
        self.close()

    def make_table_item(self, value):
        return QTableWidgetItem(str(value))

    def default_monitor_rows(self):
        return [
            {"keyword": "Mac mini M4", "min_price": 2500, "max_price": 3500, "pages": 1},
            {"keyword": "Xeon E5 2696 V4", "min_price": 100, "max_price": 200, "pages": 1},
        ]

    def config_table_rows(self):
        rows = []
        for row in range(self.config_table.rowCount()):
            values = []
            for column in range(4):
                item = self.config_table.item(row, column)
                values.append(item.text().strip() if item else "")
            rows.append(
                {
                    "keyword": values[0],
                    "min_price": values[1],
                    "max_price": values[2],
                    "pages": values[3],
                }
            )
        return rows

    def apply_monitor_rows(self, rows):
        self.config_table.setRowCount(0)
        if not isinstance(rows, list) or not rows:
            rows = self.default_monitor_rows()

        for row in rows[:MAX_MONITOR_ROWS]:
            if not isinstance(row, dict):
                continue
            self.add_monitor_row(
                limit_text(row.get("keyword", ""), 80),
                clamp_int(row.get("min_price", 0), 0, 0, MAX_PRICE_VALUE),
                clamp_int(row.get("max_price", 999999), 999999, 0, MAX_PRICE_VALUE),
                clamp_int(row.get("pages", 1), 1, 1, MAX_SCAN_PAGES),
            )
        if self.config_table.rowCount() == 0:
            for row in self.default_monitor_rows():
                self.add_monitor_row(
                    row["keyword"],
                    row["min_price"],
                    row["max_price"],
                    row["pages"],
                )

    def current_settings(self):
        return {
            "version": 1,
            "monitor_rows": self.config_table_rows(),
            "interval_min": self.interval_min_input.value(),
            "interval_max": self.interval_max_input.value(),
            "smart_filter": self.smart_filter_checkbox.isChecked(),
            "smart_match": self.smart_match_checkbox.isChecked(),
            "prefer_personal": self.personal_filter_checkbox.isChecked(),
            "min_alert_score": self.min_alert_score_input.value(),
            "black_words": self.black_words_input.text(),
            "platforms": {
                "xianyu": self.platform_xianyu_checkbox.isChecked(),
                "jd": self.platform_jd_checkbox.isChecked(),
                "taobao": self.platform_taobao_checkbox.isChecked(),
            },
            "rule_options": self.build_rule_options(),
        }

    def load_saved_settings(self):
        settings = load_app_settings()
        if not settings:
            return False

        self.suspend_settings_save = True
        try:
            self.apply_monitor_rows(settings.get("monitor_rows", []))
            self.interval_min_input.setValue(int(settings.get("interval_min", 180)))
            self.interval_max_input.setValue(int(settings.get("interval_max", 300)))
            self.smart_filter_checkbox.setChecked(bool(settings.get("smart_filter", True)))
            self.smart_match_checkbox.setChecked(bool(settings.get("smart_match", True)))
            self.personal_filter_checkbox.setChecked(bool(settings.get("prefer_personal", True)))
            self.min_alert_score_input.setValue(int(settings.get("min_alert_score", 55)))
            self.black_words_input.setText(str(settings.get("black_words", "")))

            platforms = settings.get("platforms", {})
            if isinstance(platforms, dict):
                self.platform_xianyu_checkbox.setChecked(bool(platforms.get("xianyu", True)))
                self.platform_jd_checkbox.setChecked(bool(platforms.get("jd", False)))
                self.platform_taobao_checkbox.setChecked(bool(platforms.get("taobao", False)))

            rule_options = settings.get("rule_options", {})
            if isinstance(rule_options, dict):
                self.filter_accessories_checkbox.setChecked(bool(rule_options.get("filter_accessories", True)))
                self.filter_empty_boxes_checkbox.setChecked(bool(rule_options.get("filter_empty_boxes", True)))
                self.filter_services_checkbox.setChecked(bool(rule_options.get("filter_services", True)))
                self.filter_bundles_checkbox.setChecked(bool(rule_options.get("filter_bundles", True)))
                self.merchant_penalty_checkbox.setChecked(bool(rule_options.get("merchant_penalty", True)))
        except Exception as exc:
            self.append_log(f"[配置] 恢复上次配置失败，已使用默认配置：{exc}")
            return False
        finally:
            self.suspend_settings_save = False

        self.settings_loaded = True
        self.append_log("[配置] 已恢复上次监测配置。")
        return True

    def setup_settings_autosave(self):
        self.config_table.itemChanged.connect(self.schedule_settings_save)
        for spin_box in (
            self.interval_min_input,
            self.interval_max_input,
            self.min_alert_score_input,
        ):
            spin_box.valueChanged.connect(self.schedule_settings_save)
        for checkbox in (
            self.smart_filter_checkbox,
            self.smart_match_checkbox,
            self.personal_filter_checkbox,
            self.platform_xianyu_checkbox,
            self.platform_jd_checkbox,
            self.platform_taobao_checkbox,
            self.filter_accessories_checkbox,
            self.filter_empty_boxes_checkbox,
            self.filter_services_checkbox,
            self.filter_bundles_checkbox,
            self.merchant_penalty_checkbox,
        ):
            checkbox.stateChanged.connect(self.schedule_settings_save)
        self.black_words_input.textChanged.connect(self.schedule_settings_save)

    def schedule_settings_save(self, *_args):
        if self.suspend_settings_save:
            return
        self.settings_save_timer.start(800)

    def save_current_settings(self):
        if self.suspend_settings_save:
            return False
        try:
            save_app_settings(self.current_settings())
        except Exception as exc:
            self.append_log(f"[配置] 自动保存失败：{exc}")
            return False
        return True

    def refresh_process_status(self):
        processes = monitor_processes()
        other_processes = [process for process in processes if not process["is_current"]]
        current_count = len(processes) - len(other_processes)
        self.stop_other_processes_button.setEnabled(bool(other_processes))
        if not processes:
            self.process_status_label.setText(f"当前 PID {os.getpid()}，未检测到后台实例")
            return []

        other_pids = "、".join(str(process["pid"]) for process in other_processes[:4])
        other_text = f"，旧实例 PID：{other_pids}" if other_pids else ""
        self.process_status_label.setText(
            f"当前 PID {os.getpid()}，当前窗口 {current_count} 个，其他实例 {len(other_processes)} 个{other_text}"
        )
        if other_processes:
            self.append_log(
                "[进程管理] 检测到其他后台实例："
                + "；".join(
                    f"PID {process['pid']}，启动时间 {process['created_at'] or '未知'}"
                    for process in other_processes[:5]
                )
            )
        return processes

    def stop_other_instances(self):
        processes = self.refresh_process_status()
        other_processes = [process for process in processes if not process["is_current"]]
        if not other_processes:
            QMessageBox.information(self, "无需处理", "没有检测到其他后台实例。")
            return

        detail_lines = [
            f"PID {process['pid']}，启动时间：{process['created_at'] or '未知'}"
            for process in other_processes
        ]
        answer = QMessageBox.question(
            self,
            "确认结束其他实例",
            "将结束以下旧的后台实例，当前窗口会保留：\n\n"
            + "\n".join(detail_lines[:8])
            + ("\n..." if len(detail_lines) > 8 else "")
            + "\n\n确定继续吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        stopped = 0
        failures = []
        for process in other_processes:
            ok, message = terminate_process(process["pid"], expected_process=process)
            if ok:
                stopped += 1
            else:
                failures.append(f"PID {process['pid']}：{message}")

        self.refresh_process_status()
        if failures:
            self.append_log("[进程管理] 部分旧实例未能结束：" + "；".join(failures[:3]))
            QMessageBox.warning(
                self,
                "部分失败",
                f"已结束 {stopped} 个旧实例，{len(failures)} 个未能结束。请查看日志。",
            )
            return

        self.append_log(f"[进程管理] 已结束 {stopped} 个旧的后台实例。")
        QMessageBox.information(self, "处理完成", f"已结束 {stopped} 个旧的后台实例。")

    def add_monitor_row(self, keyword="", min_price=0, max_price=999999, pages=1):
        row = self.config_table.rowCount()
        self.config_table.insertRow(row)
        self.config_table.setItem(row, 0, self.make_table_item(keyword))
        self.config_table.setItem(row, 1, self.make_table_item(min_price))
        self.config_table.setItem(row, 2, self.make_table_item(max_price))
        self.config_table.setItem(row, 3, self.make_table_item(pages))
        self.refresh_dashboard_summary()

    def add_empty_monitor_row(self):
        if self.config_table.rowCount() >= MAX_MONITOR_ROWS:
            QMessageBox.warning(self, "已达上限", f"最多只能监测 {MAX_MONITOR_ROWS} 个商品。")
            return
        self.add_monitor_row()
        self.schedule_settings_save()

    def remove_selected_monitor_rows(self):
        rows = sorted(
            {index.row() for index in self.config_table.selectedIndexes()},
            reverse=True,
        )
        if not rows:
            QMessageBox.information(self, "提示", "请先选中要删除的商品行。")
            return

        for row in rows:
            self.config_table.removeRow(row)
        self.schedule_settings_save()
        self.refresh_dashboard_summary()

    def append_log(self, message):
        if self.should_summarize_log(message):
            self.append_full_log_line(message)
            self.collect_log_noise(message)
            return

        self.flush_log_noise_summary()
        self.append_log_line(message)

    def append_log_line(self, message):
        self.log_output.append(message)
        if self.is_important_log(message):
            self.important_log_output.append(message)
        try:
            append_monitor_log(message)
        except Exception as exc:
            if not self.log_write_failed:
                self.log_write_failed = True
                warning = f"[日志] 写入监测日志失败：{exc}"
                self.log_output.append(warning)
                self.important_log_output.append(warning)

    def append_full_log_line(self, message):
        self.log_output.append(message)
        try:
            append_monitor_log(message)
        except Exception as exc:
            if not self.log_write_failed:
                self.log_write_failed = True
                warning = f"[日志] 写入监测日志失败：{exc}"
                self.log_output.append(warning)
                self.important_log_output.append(warning)

    def should_summarize_log(self, message):
        noisy_markers = (
            "排除商品类型不匹配",
            "排除求购/回收结果",
            "排除已学习误报",
            "排除低质量结果",
            "低分结果不提醒",
            "正在检查 Chrome 调试端口",
            "正在通过 CDP 接管本地 Chrome",
            "正在刷新数据",
            "正在监测商品",
            "正在监测平台",
            "正在打开",
            "搜索页打开失败",
            "正在应用筛选",
            "正在解析第",
            "正在触发平台商品流懒加载",
            "页面商品流已加载",
            "检测到 ",
            "本轮扫描结束",
        )
        return any(marker in message for marker in noisy_markers)

    def is_important_log(self, message):
        important_markers = (
            "[命中]",
            "命中目标",
            "[错误]",
            "异常",
            "失败",
            "[智能建议]",
            "[智能价格]",
            "[比价]",
            "[操作]",
            "[批量]",
            "[学习]",
            "[缓存清理]",
            "[进程管理]",
            "[环境检查]",
            "[环境守护]",
            "[历史命中]",
            "[日志降噪]",
            "风控",
            "登录",
            "验证",
        )
        return any(marker in message for marker in important_markers)

    def collect_log_noise(self, message):
        category = self.log_noise_category(message)
        record = self.log_noise_buffer.setdefault(
            category,
            {"count": 0, "sample": ""},
        )
        record["count"] += 1
        if not record["sample"]:
            record["sample"] = self.shorten_text(message, 90)
        if not self.log_summary_timer.isActive():
            self.log_summary_timer.start()

    def log_noise_category(self, message):
        if "商品类型不匹配" in message:
            return "类型不匹配"
        if "求购/回收" in message:
            return "求购/回收"
        if "已学习误报" in message:
            return "已学习误报"
        if "低质量结果" in message:
            return "排除词"
        if "低分结果" in message:
            return "低分"
        if "刷新数据" in message or "本轮扫描结束" in message:
            return "轮询状态"
        if "正在监测" in message or "正在打开" in message:
            return "扫描进度"
        if "商品流" in message or "候选商品" in message or "正在解析" in message:
            return "页面解析"
        if "Chrome" in message or "CDP" in message:
            return "浏览器接管"
        return "过滤"

    def flush_log_noise_summary(self):
        if not self.log_noise_buffer:
            if self.log_summary_timer.isActive():
                self.log_summary_timer.stop()
            return

        parts = []
        samples = []
        for category, record in sorted(self.log_noise_buffer.items()):
            parts.append(f"{category} {record['count']} 条")
            if record.get("sample"):
                samples.append(record["sample"])
        summary = "[日志降噪] 已汇总过滤明细：" + "，".join(parts)
        if samples:
            summary += "。示例：" + "；".join(samples[:2])
        self.log_noise_buffer = {}
        if self.log_summary_timer.isActive():
            self.log_summary_timer.stop()
        self.append_log_line(summary)

    def append_error(self, message):
        self.append_log(f"[错误] {message}")

    def item_status_key(self, item):
        return (
            item.get("url")
            or item.get("item_id")
            or normalize_title_key(item.get("title", ""))
        )

    def status_for_item(self, item):
        key = self.item_status_key(item)
        record = self.item_statuses.get(key, {})
        status = record.get("status", HIT_STATUS_DEFAULT)
        return status if status in HIT_STATUS_OPTIONS else HIT_STATUS_DEFAULT

    def persist_item_statuses(self):
        try:
            save_item_statuses(self.item_statuses)
        except Exception as exc:
            QMessageBox.warning(self, "状态保存失败", f"保存命中状态失败：{exc}")
            return False
        return True

    def set_item_status(self, item, status):
        if status not in HIT_STATUS_OPTIONS:
            status = HIT_STATUS_DEFAULT
        key = self.item_status_key(item)
        if not key:
            return False
        item["status"] = status
        self.item_statuses[key] = {
            "status": status,
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "keyword": item.get("keyword", ""),
            "title": item.get("title", ""),
            "url": item.get("url", ""),
        }
        return self.persist_item_statuses()

    def set_selected_result_status(self, status):
        row, item = self.selected_found_item()
        if item is None:
            return
        if not self.set_item_status(item, status):
            return
        self.result_table.setItem(row, 1, self.make_table_item(status))
        self.save_hit_history_now()
        self.apply_result_sort_and_filter()
        row = self.result_row_for_item_index(self.found_items.index(item))
        self.update_result_detail(item, row)
        self.append_log(
            f"[状态] {status}：{item.get('keyword', '')} | "
            f"{self.shorten_text(item.get('title', ''), 80)}"
        )
        self.refresh_dashboard_summary()

    def add_result_row(self, item, found_time=None):
        if found_time is None:
            found_time = item.get("time") or time.strftime("%Y-%m-%d %H:%M:%S")
        item["time"] = found_time
        row = self.result_table.rowCount()
        item_index = len(self.found_items) - 1
        self.result_table.insertRow(row)
        time_item = self.make_table_item(found_time)
        time_item.setData(Qt.ItemDataRole.UserRole, item_index)
        self.result_table.setItem(row, 0, time_item)
        self.result_table.setItem(row, 1, self.make_table_item(item["status"]))
        self.result_table.setItem(row, 2, self.make_table_item(item.get("platform_name", "闲鱼")))
        self.result_table.setItem(row, 3, self.make_table_item(item["keyword"]))
        self.result_table.setItem(row, 4, self.make_table_item(item.get("page_number", 1)))
        price_item = self.make_table_item(item["price"])
        price_item.setData(Qt.ItemDataRole.UserRole, self.numeric_sort_value(item.get("price")))
        self.result_table.setItem(row, 5, price_item)
        score_item = self.make_table_item(item.get("score", ""))
        score_item.setData(Qt.ItemDataRole.UserRole, self.numeric_sort_value(item.get("score")))
        self.result_table.setItem(row, 6, score_item)
        self.result_table.setItem(row, 7, self.make_table_item(item.get("level", "")))
        self.result_table.setItem(row, 8, self.make_table_item(item.get("quality_reason", "")))
        self.result_table.setItem(row, 9, self.make_table_item(item["title"]))
        self.result_table.setItem(row, 10, self.make_table_item(item["url"]))
        self.apply_result_sort_and_filter()
        if self.result_table.rowCount() == 1:
            self.result_table.selectRow(0)
        self.result_table.scrollToBottom()
        self.refresh_dashboard_summary()

    def numeric_sort_value(self, value):
        try:
            return float(value)
        except (TypeError, ValueError):
            return -1.0

    def result_item_index_for_row(self, row):
        if row is None or row < 0 or row >= self.result_table.rowCount():
            return None
        index_item = self.result_table.item(row, 0)
        if not index_item:
            return None
        item_index = index_item.data(Qt.ItemDataRole.UserRole)
        if item_index is None:
            return None
        try:
            item_index = int(item_index)
        except (TypeError, ValueError):
            return None
        if item_index < 0 or item_index >= len(self.found_items):
            return None
        return item_index

    def item_for_result_row(self, row):
        item_index = self.result_item_index_for_row(row)
        if item_index is None:
            return None
        return self.found_items[item_index]

    def result_row_for_item_index(self, item_index):
        for row in range(self.result_table.rowCount()):
            if self.result_item_index_for_row(row) == item_index:
                return row
        return None

    def refresh_result_row_indexes(self):
        for row in range(self.result_table.rowCount()):
            item = self.item_for_result_row(row)
            if item is None:
                continue
            index_item = self.result_table.item(row, 0)
            if index_item:
                index_item.setData(Qt.ItemDataRole.UserRole, self.found_items.index(item))

    def apply_result_sort_and_filter(self, *_args):
        self.sort_result_table()
        self.apply_result_filter()

    def sort_result_table(self):
        sort_text = self.result_sort_combo.currentText()
        sort_map = {
            "按时间最新": (0, Qt.SortOrder.DescendingOrder),
            "按价格最低": (5, Qt.SortOrder.AscendingOrder),
            "按价格最高": (5, Qt.SortOrder.DescendingOrder),
            "按评分最高": (6, Qt.SortOrder.DescendingOrder),
            "按平台": (2, Qt.SortOrder.AscendingOrder),
            "按状态": (1, Qt.SortOrder.AscendingOrder),
        }
        column, order = sort_map.get(sort_text, (0, Qt.SortOrder.DescendingOrder))
        self.result_table.sortItems(column, order)

    def apply_result_filter(self, *_args):
        query = self.normalize_text(self.result_search_input.text())
        status_filter = self.result_status_filter.currentText()
        platform_filter = self.result_platform_filter.currentText()
        group_filter = self.active_result_group_filter
        visible_count = 0
        total_count = self.result_table.rowCount()

        for row in range(total_count):
            item = self.item_for_result_row(row) or {}
            row_text = self.normalize_text(
                " ".join(
                    str(item.get(field, ""))
                    for field in (
                        "time",
                        "status",
                        "platform_name",
                        "keyword",
                        "price",
                        "score",
                        "level",
                        "quality_reason",
                        "title",
                        "url",
                    )
                )
            )
            status_ok = (
                status_filter == "全部状态"
                or item.get("status", HIT_STATUS_DEFAULT) == status_filter
            )
            favorite_ok = (
                not self.only_favorites_button.isChecked()
                or item.get("status", HIT_STATUS_DEFAULT) == "收藏"
            )
            platform_ok = (
                platform_filter == "全部平台"
                or item.get("platform_name", "闲鱼") == platform_filter
            )
            query_ok = not query or query in row_text
            group_ok = self.result_item_matches_group_filter(item, group_filter)
            is_visible = status_ok and favorite_ok and platform_ok and query_ok and group_ok
            self.result_table.setRowHidden(row, not is_visible)
            if is_visible:
                visible_count += 1

        if total_count == visible_count:
            self.result_filter_label.setText(f"显示全部 {total_count} 条")
        else:
            self.result_filter_label.setText(f"显示 {visible_count}/{total_count} 条")
        self.update_result_groups()
        self.ensure_visible_result_selection()

    def toggle_only_favorites(self, checked):
        self.only_favorites_button.setText("显示全部" if checked else "只看收藏")
        self.result_status_filter.blockSignals(True)
        if checked:
            self.result_status_filter.setCurrentText("全部状态")
        self.result_status_filter.blockSignals(False)
        self.apply_result_sort_and_filter()

    def clear_result_filters(self):
        self.active_result_group_filter = None
        self.result_search_input.clear()
        self.result_status_filter.setCurrentText("全部状态")
        self.result_platform_filter.setCurrentText("全部平台")
        self.only_favorites_button.setChecked(False)
        self.apply_result_sort_and_filter()

    def on_result_group_type_changed(self, *_args):
        self.active_result_group_filter = None
        self.update_result_groups()

    def result_item_matches_group_filter(self, item, group_filter=None):
        if not group_filter:
            return True
        group_type, group_value = group_filter
        if group_type == "按平台":
            return (item.get("platform_name", "闲鱼") or "未知平台") == group_value
        if group_type == "按状态":
            return (item.get("status", HIT_STATUS_DEFAULT) or HIT_STATUS_DEFAULT) == group_value
        return (item.get("keyword", "") or "未命名关键词") == group_value

    def visible_result_rows_and_items(self):
        pairs = []
        for row in range(self.result_table.rowCount()):
            item = self.item_for_result_row(row)
            if item is not None and not self.result_table.isRowHidden(row):
                pairs.append((row, item))
        return pairs

    def result_group_key(self, item):
        group_type = self.result_group_type_combo.currentText()
        if group_type == "按平台":
            return item.get("platform_name", "闲鱼") or "未知平台"
        if group_type == "按状态":
            return item.get("status", HIT_STATUS_DEFAULT) or HIT_STATUS_DEFAULT
        return item.get("keyword", "") or "未命名关键词"

    def update_result_groups(self, *_args):
        if not hasattr(self, "result_group_table"):
            return
        groups = {}
        for _row, item in self.visible_result_rows_and_items():
            key = self.result_group_key(item)
            record = groups.setdefault(
                key,
                {
                    "count": 0,
                    "pending": 0,
                    "favorite": 0,
                    "min_price": None,
                    "max_score": None,
                },
            )
            record["count"] += 1
            if item.get("status", HIT_STATUS_DEFAULT) == HIT_STATUS_DEFAULT:
                record["pending"] += 1
            if item.get("status") == "收藏":
                record["favorite"] += 1
            price = self.numeric_sort_value(item.get("price"))
            if price >= 0 and (record["min_price"] is None or price < record["min_price"]):
                record["min_price"] = price
            score = self.numeric_sort_value(item.get("score"))
            if score >= 0 and (record["max_score"] is None or score > record["max_score"]):
                record["max_score"] = score

        self.result_group_table.setRowCount(0)
        for key, record in sorted(groups.items(), key=lambda kv: (-kv[1]["count"], kv[0])):
            row = self.result_group_table.rowCount()
            self.result_group_table.insertRow(row)
            group_item = self.make_table_item(key)
            group_item.setData(Qt.ItemDataRole.UserRole, key)
            self.result_group_table.setItem(row, 0, group_item)
            self.result_group_table.setItem(row, 1, self.make_table_item(record["count"]))
            self.result_group_table.setItem(row, 2, self.make_table_item(record["pending"]))
            self.result_group_table.setItem(row, 3, self.make_table_item(record["favorite"]))
            min_price = "" if record["min_price"] is None else int(record["min_price"])
            max_score = "" if record["max_score"] is None else int(record["max_score"])
            self.result_group_table.setItem(row, 4, self.make_table_item(min_price))
            self.result_group_table.setItem(row, 5, self.make_table_item(max_score))

    def apply_result_group_filter(self, row, _column):
        group_item = self.result_group_table.item(row, 0)
        if not group_item:
            return
        group_value = str(group_item.data(Qt.ItemDataRole.UserRole) or group_item.text())
        group_type = self.result_group_type_combo.currentText()
        self.active_result_group_filter = (group_type, group_value)
        if group_type == "按平台":
            if self.only_favorites_button.isChecked():
                self.only_favorites_button.setChecked(False)
            self.result_platform_filter.setCurrentText(group_value)
        elif group_type == "按状态":
            self.result_status_filter.setCurrentText(group_value)
            if group_value != "收藏" and self.only_favorites_button.isChecked():
                self.only_favorites_button.setChecked(False)
        else:
            if self.only_favorites_button.isChecked():
                self.only_favorites_button.setChecked(False)
        self.apply_result_sort_and_filter()

    def batch_set_visible_status(self, status):
        pairs = self.visible_result_rows_and_items()
        if not pairs:
            QMessageBox.information(self, "提示", "当前没有可批量处理的可见结果。")
            return False
        changed = 0
        for row, item in pairs:
            if self.set_item_status(item, status):
                self.result_table.setItem(row, 1, self.make_table_item(status))
                changed += 1
        if changed:
            self.save_hit_history_now()
            self.apply_result_sort_and_filter()
            self.append_log(f"[批量] 已将 {changed} 条可见结果标记为：{status}")
        return bool(changed)

    def ensure_visible_result_selection(self):
        selected_row = self.selected_result_row(show_message=False)
        if selected_row is not None and selected_row < self.result_table.rowCount():
            if not self.result_table.isRowHidden(selected_row):
                self.update_result_detail_from_selection()
                return

        self.result_table.clearSelection()
        for row in range(self.result_table.rowCount()):
            if not self.result_table.isRowHidden(row):
                self.result_table.selectRow(row)
                self.update_result_detail_from_selection()
                return
        self.clear_result_detail()

    def clear_result_detail(self):
        self.result_detail_summary_label.setText("选中一条命中结果后，这里显示完整信息。")
        self.result_detail_title_label.setText("标题：-")
        self.result_detail_reason_label.setText("理由：-")
        self.result_detail_status_label.setText("状态：-")
        self.result_detail_url_label.setText("链接：-")

    def update_result_detail_from_selection(self):
        row = self.selected_result_row(show_message=False)
        item = self.item_for_result_row(row)
        if row is None or item is None or self.result_table.isRowHidden(row):
            self.clear_result_detail()
            return
        self.update_result_detail(item, row)

    def update_result_detail(self, item, row=None):
        row_label = f"第 {row + 1} 条 | " if row is not None else ""
        self.result_detail_summary_label.setText(
            f"{row_label}{item.get('platform_name', '闲鱼')} | "
            f"{item.get('keyword', '')} | {item.get('price', '')} 元 | "
            f"{item.get('level', '')} {item.get('score', '')}分"
        )
        self.result_detail_title_label.setText(
            f"标题：{item.get('title', '-')}"
        )
        self.result_detail_reason_label.setText(
            f"理由：{item.get('quality_reason', '-')}"
        )
        self.result_detail_status_label.setText(
            f"状态：{item.get('status', HIT_STATUS_DEFAULT)} | "
            f"时间：{item.get('time', '-')} | 页码：{item.get('page_number', '-')}"
        )
        self.result_detail_url_label.setText(f"链接：{item.get('url', '-')}")

    def visible_result_items(self):
        return [item for _row, item in self.visible_result_rows_and_items()]

    def result_export_headers(self):
        return [
            "时间",
            "状态",
            "平台",
            "关键词",
            "页码",
            "价格",
            "评分",
            "等级",
            "理由",
            "标题",
            "链接",
        ]

    def result_export_row(self, item):
        return [
            item.get("time", ""),
            item.get("status", HIT_STATUS_DEFAULT),
            item.get("platform_name", "闲鱼"),
            item.get("keyword", ""),
            item.get("page_number", ""),
            item.get("price", ""),
            item.get("score", ""),
            item.get("level", ""),
            item.get("quality_reason", ""),
            item.get("title", ""),
            item.get("url", ""),
        ]

    def default_results_export_path(self, suffix=".csv"):
        filename = f"命中结果_{time.strftime('%Y%m%d_%H%M%S')}{suffix}"
        return os.path.abspath(filename)

    def export_results(self):
        items = self.visible_result_items()
        if not items:
            QMessageBox.information(self, "提示", "当前没有可导出的命中结果。")
            return False

        default_path = self.default_results_export_path(".csv")
        file_path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "导出命中结果",
            default_path,
            "CSV 文件 (*.csv);;Excel 文件 (*.xlsx)",
        )
        if not file_path:
            return False

        if selected_filter.startswith("Excel") and not file_path.lower().endswith(".xlsx"):
            file_path += ".xlsx"
        elif selected_filter.startswith("CSV") and not file_path.lower().endswith(".csv"):
            file_path += ".csv"

        try:
            self.export_results_to_file(file_path, items)
        except Exception as exc:
            QMessageBox.warning(self, "导出失败", f"导出命中结果失败：{exc}")
            return False

        self.append_log(f"[操作] 已导出 {len(items)} 条命中结果：{file_path}")
        QMessageBox.information(self, "导出成功", f"已导出 {len(items)} 条命中结果：\n{file_path}")
        return True

    def export_results_to_file(self, file_path, items=None):
        items = self.visible_result_items() if items is None else list(items)
        if not items:
            raise ValueError("没有可导出的命中结果")

        if file_path.lower().endswith(".xlsx"):
            return self.export_results_to_xlsx(file_path, items)
        return self.export_results_to_csv(file_path, items)

    def export_results_to_csv(self, file_path, items):
        with open(file_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(self.result_export_headers())
            for item in items:
                writer.writerow(self.result_export_row(item))
        return file_path

    def export_results_to_xlsx(self, file_path, items):
        try:
            from openpyxl import Workbook
        except ImportError as exc:
            raise RuntimeError("当前环境未安装 openpyxl，请先导出 CSV 文件。") from exc

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "命中结果"
        sheet.append(self.result_export_headers())
        for item in items:
            sheet.append(self.result_export_row(item))
        for column_cells in sheet.columns:
            max_length = max(
                len(str(cell.value)) if cell.value is not None else 0
                for cell in column_cells
            )
            sheet.column_dimensions[column_cells[0].column_letter].width = min(
                max(max_length + 2, 10),
                60,
            )
        workbook.save(file_path)
        return file_path

    def save_hit_history_now(self):
        try:
            save_hit_history(self.found_items)
        except Exception as exc:
            self.append_log(f"[历史命中] 保存失败：{exc}")
            return False
        return True

    def load_saved_hits(self):
        saved_hits = load_hit_history()
        if not saved_hits:
            return False

        for item in saved_hits[-500:]:
            if not isinstance(item, dict):
                continue
            item["status"] = self.status_for_item(item)
            self.found_items.append(item)
            self.add_result_row(item, item.get("time"))
        self.append_log(f"[历史命中] 已恢复 {len(self.found_items)} 条上次保存的命中结果。")
        return True

    def on_item_found(self, item):
        item["status"] = self.status_for_item(item)
        self.found_items.append(item)
        self.add_result_row(item)
        self.save_hit_history_now()
        self.append_log(
            f"[命中] {item.get('platform_name', '闲鱼')} | {item['keyword']} | 第 {item.get('page_number', 1)} 页 | "
            f"{item['price']} 元 | {item.get('level', '')} {item.get('score', '')}分 | "
            f"{self.shorten_text(item['title'], 100)} | {item['url']}"
        )

    def format_platform_price(self, comparison, platform_key):
        platform_data = comparison.get("platforms", {}).get(platform_key)
        if not platform_data:
            return "-"
        return f"{platform_data['price']} 元"

    def on_comparison_ready(self, comparison):
        row = self.comparison_table.rowCount()
        found_time = time.strftime("%Y-%m-%d %H:%M:%S")
        self.comparison_items.append(comparison)
        self.comparison_table.insertRow(row)
        self.comparison_table.setItem(row, 0, self.make_table_item(found_time))
        self.comparison_table.setItem(row, 1, self.make_table_item(comparison.get("keyword", "")))
        self.comparison_table.setItem(row, 2, self.make_table_item(self.format_platform_price(comparison, "xianyu")))
        self.comparison_table.setItem(row, 3, self.make_table_item(self.format_platform_price(comparison, "jd")))
        self.comparison_table.setItem(row, 4, self.make_table_item(self.format_platform_price(comparison, "taobao")))
        self.comparison_table.setItem(row, 5, self.make_table_item(comparison.get("best_platform_name", "")))
        self.comparison_table.setItem(row, 6, self.make_table_item(comparison.get("best_url", "")))
        self.comparison_table.scrollToBottom()
        suggestion = comparison.get("price_suggestion")
        if suggestion:
            self.on_price_suggestion_ready(suggestion)

    def on_price_suggestion_ready(self, suggestion):
        row = self.price_suggestion_table.rowCount()
        found_time = time.strftime("%Y-%m-%d %H:%M:%S")
        suggestion = dict(suggestion)
        suggestion["time"] = found_time
        self.price_suggestion_items.append(suggestion)
        self.price_suggestion_table.insertRow(row)
        current_range = (
            f"{suggestion['current_min_price']}-"
            f"{suggestion['current_max_price']}"
        )
        suggested_range = (
            f"{suggestion['suggested_min_price']}-"
            f"{suggestion['suggested_max_price']}"
        )
        self.price_suggestion_table.setItem(row, 0, self.make_table_item(found_time))
        self.price_suggestion_table.setItem(row, 1, self.make_table_item(suggestion["keyword"]))
        self.price_suggestion_table.setItem(
            row,
            2,
            self.make_table_item(
                f"{suggestion['platform_name']} {suggestion['best_price']} 元"
            ),
        )
        self.price_suggestion_table.setItem(row, 3, self.make_table_item(current_range))
        self.price_suggestion_table.setItem(row, 4, self.make_table_item(suggested_range))
        self.price_suggestion_table.setItem(row, 5, self.make_table_item(suggestion["reason"]))
        self.price_suggestion_table.scrollToBottom()
        self.refresh_dashboard_summary()

    def selected_price_suggestion_row(self):
        selected = self.price_suggestion_table.selectedIndexes()
        if not selected:
            return None
        return selected[0].row()

    def find_config_row_by_keyword(self, keyword):
        normalized_keyword = self.normalize_text(keyword)
        for row in range(self.config_table.rowCount()):
            item = self.config_table.item(row, 0)
            if item and self.normalize_text(item.text()) == normalized_keyword:
                return row
        return None

    def sync_worker_price_config(self, keyword, min_price, max_price):
        if not self.worker:
            return
        normalized_keyword = self.normalize_text(keyword)
        for config_item in self.worker.config:
            if self.normalize_text(config_item.get("keyword", "")) == normalized_keyword:
                config_item["min_price"] = min_price
                config_item["max_price"] = max_price

    def apply_price_suggestion(self, row):
        if row is None or row >= len(self.price_suggestion_items):
            QMessageBox.information(self, "提示", "请先选中一条价格建议。")
            return False

        suggestion = self.price_suggestion_items[row]
        keyword = suggestion["keyword"]
        config_row = self.find_config_row_by_keyword(keyword)
        if config_row is None:
            QMessageBox.warning(self, "应用失败", f"没有找到配置里的商品：{keyword}")
            return False

        min_price = suggestion["suggested_min_price"]
        max_price = suggestion["suggested_max_price"]
        self.config_table.setItem(config_row, 1, self.make_table_item(min_price))
        self.config_table.setItem(config_row, 2, self.make_table_item(max_price))
        self.sync_worker_price_config(keyword, min_price, max_price)
        self.schedule_settings_save()
        self.append_log(
            f"[智能价格] 已应用建议：{keyword} 价格区间调整为 "
            f"{min_price}-{max_price} 元。"
        )
        return True

    def apply_selected_price_suggestion(self):
        row = self.selected_price_suggestion_row()
        if self.apply_price_suggestion(row):
            self.ignore_price_suggestion(row)

    def apply_latest_price_suggestion(self):
        if not self.price_suggestion_items:
            QMessageBox.information(self, "提示", "当前没有可应用的价格建议。")
            return
        row = len(self.price_suggestion_items) - 1
        self.price_suggestion_table.selectRow(row)
        if self.apply_price_suggestion(row):
            self.ignore_price_suggestion(row)

    def ignore_price_suggestion(self, row):
        if row is None or row >= len(self.price_suggestion_items):
            return
        self.price_suggestion_items.pop(row)
        self.price_suggestion_table.removeRow(row)

    def ignore_selected_price_suggestion(self):
        row = self.selected_price_suggestion_row()
        if row is None:
            QMessageBox.information(self, "提示", "请先选中一条价格建议。")
            return
        self.ignore_price_suggestion(row)

    def open_comparison_link_at_row(self, row, _column):
        if row >= len(self.comparison_items):
            return
        best_url = self.comparison_items[row].get("best_url", "")
        if best_url:
            QDesktopServices.openUrl(QUrl.fromUserInput(best_url))

    def build_config(self):
        interval_min = self.interval_min_input.value()
        interval_max = self.interval_max_input.value()
        if interval_min > interval_max:
            raise ValueError("最短间隔不能大于最长间隔。")
        if self.config_table.rowCount() > MAX_MONITOR_ROWS:
            raise ValueError(f"监测商品最多 {MAX_MONITOR_ROWS} 行，请删减后再启动。")

        config = []
        for row in range(self.config_table.rowCount()):
            keyword_item = self.config_table.item(row, 0)
            min_item = self.config_table.item(row, 1)
            max_item = self.config_table.item(row, 2)
            pages_item = self.config_table.item(row, 3)

            keyword = keyword_item.text().strip() if keyword_item else ""
            if not keyword:
                raise ValueError(f"第 {row + 1} 行关键词不能为空。")
            if len(keyword) > 80:
                raise ValueError(f"第 {row + 1} 行关键词过长，请控制在 80 个字符内。")

            try:
                min_price = int((min_item.text() if min_item else "").strip())
                max_price = int((max_item.text() if max_item else "").strip())
                pages = int((pages_item.text() if pages_item else "").strip())
            except ValueError as exc:
                raise ValueError(f"第 {row + 1} 行价格和扫描页数必须是整数。") from exc

            if min_price < 0 or max_price < 0:
                raise ValueError(f"第 {row + 1} 行价格不能为负数。")
            if min_price > MAX_PRICE_VALUE or max_price > MAX_PRICE_VALUE:
                raise ValueError(f"第 {row + 1} 行价格不能超过 {MAX_PRICE_VALUE}。")

            if min_price > max_price:
                raise ValueError(f"第 {row + 1} 行最低价不能大于最高价。")

            if pages < 1:
                raise ValueError(f"第 {row + 1} 行扫描页数至少为 1。")
            if pages > MAX_SCAN_PAGES:
                raise ValueError(f"第 {row + 1} 行扫描页数最多 {MAX_SCAN_PAGES} 页。")

            config.append(
                {
                "keyword": limit_text(keyword, 80),
                    "min_price": min_price,
                    "max_price": max_price,
                    "pages": pages,
                }
            )

        if not config:
            raise ValueError("请至少添加一个监测商品。")

        return config

    def build_black_words(self):
        black_words = list(DEFAULT_BLACK_WORDS) if self.smart_filter_checkbox.isChecked() else []
        raw_text = self.black_words_input.text().strip()
        if not raw_text:
            return black_words

        extra_words = [
            word.strip()
            for word in re.split(r"[,，、\s]+", raw_text)
            if word.strip()
        ]
        return black_words + [word for word in extra_words if word not in black_words]

    def build_rule_options(self):
        return {
            "filter_accessories": self.filter_accessories_checkbox.isChecked(),
            "filter_empty_boxes": self.filter_empty_boxes_checkbox.isChecked(),
            "filter_services": self.filter_services_checkbox.isChecked(),
            "filter_bundles": self.filter_bundles_checkbox.isChecked(),
            "merchant_penalty": self.merchant_penalty_checkbox.isChecked(),
        }

    def build_platforms(self):
        platforms = []
        if self.platform_xianyu_checkbox.isChecked():
            platforms.append("xianyu")
        if self.platform_jd_checkbox.isChecked():
            platforms.append("jd")
        if self.platform_taobao_checkbox.isChecked():
            platforms.append("taobao")
        if not platforms:
            raise ValueError("请至少选择一个监测平台。")
        return platforms

    def shorten_text(self, text, limit=120):
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) <= limit:
            return text
        return f"{text[:limit]}..."

    def normalize_text(self, text):
        return re.sub(r"\s+", "", text.lower())

    def selected_result_row(self, show_message=True):
        selected = self.result_table.selectedIndexes()
        if not selected:
            if show_message:
                QMessageBox.information(self, "提示", "请先选中一条命中结果。")
            return None
        return selected[0].row()

    def selected_found_item(self):
        row = self.selected_result_row(show_message=False)
        if row is None:
            QMessageBox.information(self, "提示", "请先选中一条命中结果。")
            return None, None
        item = self.item_for_result_row(row)
        if item is None:
            QMessageBox.warning(self, "错误", "选中结果和内部记录不一致，请清空结果后重新监测。")
            return None, None
        return row, item

    def open_result_link_at_row(self, row, _column):
        self.open_result_link(row)

    def open_selected_result_link(self):
        row = self.selected_result_row()
        if row is None:
            QMessageBox.information(self, "提示", "请先选中一条命中结果。")
            return
        self.open_result_link(row)

    def open_result_link(self, row):
        item = self.item_for_result_row(row)
        if item is None:
            QMessageBox.warning(self, "错误", "这条结果没有可打开的链接。")
            return
        url = str(item.get("url", "")).strip()
        if not url:
            QMessageBox.warning(self, "错误", "这条结果没有可打开的链接。")
            return
        QDesktopServices.openUrl(QUrl.fromUserInput(url))
        if item.get("status", HIT_STATUS_DEFAULT) == HIT_STATUS_DEFAULT:
            if self.set_item_status(item, "已查看"):
                self.result_table.setItem(row, 1, self.make_table_item("已查看"))
                self.save_hit_history_now()
                self.apply_result_sort_and_filter()
                row = self.result_row_for_item_index(self.found_items.index(item))
                self.update_result_detail(item, row)

    def find_chrome_executable(self):
        for chrome_path in CHROME_EXE_CANDIDATES:
            if os.path.exists(chrome_path):
                return chrome_path
        return None

    def chrome_session_payload(self):
        return {
            "pid": self.owned_chrome_pid,
            "port": self.cdp_port,
            "endpoint": self.cdp_endpoint,
            "profile_dir": os.path.abspath(CHROME_PROFILE_DIR),
            "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

    def save_chrome_session(self):
        if not self.owned_chrome_pid or not self.cdp_port or not self.cdp_endpoint:
            return False
        atomic_write_json(CHROME_SESSION_FILE, self.chrome_session_payload())
        return True

    def clear_chrome_session(self):
        for path in (CHROME_SESSION_FILE,):
            if os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass

    def load_chrome_session(self):
        data = load_json_file(CHROME_SESSION_FILE, {}, dict)
        if not data:
            return {}
        try:
            data["pid"] = int(data.get("pid", 0))
            data["port"] = int(data.get("port", 0))
        except Exception:
            return {}
        data["profile_dir"] = os.path.abspath(str(data.get("profile_dir", "")))
        data["endpoint"] = str(data.get("endpoint") or cdp_endpoint(data["port"]))
        return data

    def is_cdp_endpoint_available(self, endpoint):
        try:
            with urlopen(f"{endpoint}/json/version", timeout=2) as response:
                return response.status == 200
        except Exception:
            return False

    def current_cdp_endpoint(self):
        session = self.load_chrome_session()
        if not session:
            return None
        if os.path.normcase(session.get("profile_dir", "")) != os.path.normcase(
            os.path.abspath(CHROME_PROFILE_DIR)
        ):
            return None
        if not self.is_cdp_endpoint_available(session["endpoint"]):
            return None
        if not is_owned_debug_chrome(session["pid"], CHROME_PROFILE_DIR, session["port"]):
            return None
        self.owned_chrome_pid = session["pid"]
        self.cdp_port = session["port"]
        self.cdp_endpoint = session["endpoint"]
        return self.cdp_endpoint

    def unknown_debug_port_endpoint(self):
        legacy_endpoint = cdp_endpoint(9222)
        if self.is_cdp_endpoint_available(legacy_endpoint) and legacy_endpoint != self.current_cdp_endpoint():
            return legacy_endpoint
        return None

    def check_dependencies(self):
        missing = []
        for package_name, module_name in REQUIRED_DEPENDENCIES:
            if importlib.util.find_spec(module_name) is None:
                missing.append(package_name)
        return missing

    def check_database_file(self):
        if not os.path.exists(DB_FILE):
            atomic_write_json(DB_FILE, [])

        with open(DB_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            raise ValueError("scanned_items.json 内容不是列表")

        temp_path = f"{DB_FILE}.tmp.check"
        atomic_write_json(temp_path, [])
        os.remove(temp_path)

    def check_environment(self):
        results = []
        has_error = False

        missing_deps = self.check_dependencies()
        if missing_deps:
            has_error = True
            results.append(f"依赖缺失：{', '.join(missing_deps)}")
        else:
            results.append("依赖：正常")

        try:
            self.check_database_file()
            results.append("去重文件：正常")
        except Exception as exc:
            has_error = True
            results.append(f"去重文件异常：{exc}")

        chrome_path = self.find_chrome_executable()
        if chrome_path:
            results.append(f"Chrome：已找到 {chrome_path}")
        else:
            has_error = True
            results.append("Chrome：未找到 chrome.exe")

        endpoint = self.current_cdp_endpoint()
        if endpoint:
            results.append(f"调试端口：本软件 Chrome 已打开 {endpoint}")
        elif self.unknown_debug_port_endpoint():
            has_error = True
            results.append("调试端口：检测到未知 9222 Chrome，已拒绝接管")
        else:
            has_error = True
            results.append("调试端口：本软件 Chrome 未打开，可点击“一键启动 Chrome”")

        results.append("闲鱼登录：请在可接管 Chrome 中保持已登录状态")
        status = "需要处理" if has_error else "环境正常"
        self.environment_status_label.setText(status)
        self.refresh_dashboard_summary()
        self.append_log("[环境检查] " + "；".join(results))
        return not has_error

    def launch_chrome_debug_browser(self, *_args, show_messages=True):
        existing_endpoint = self.current_cdp_endpoint()
        if existing_endpoint:
            message = f"本软件 Chrome 已可用：{existing_endpoint}"
            self.environment_status_label.setText("环境正常")
            self.refresh_dashboard_summary()
            self.append_log(f"[环境守护] {message}")
            if show_messages:
                QMessageBox.information(self, "Chrome 已可用", message)
            return True

        unknown_endpoint = self.unknown_debug_port_endpoint()
        if unknown_endpoint:
            message = (
                f"检测到未知 Chrome 调试端口：{unknown_endpoint}。"
                "为保护登录态，软件不会接管未知浏览器。请关闭该 Chrome 后重试。"
            )
            self.environment_status_label.setText("需要处理")
            self.refresh_dashboard_summary()
            self.append_log(f"[环境守护] {message}")
            if show_messages:
                QMessageBox.warning(self, "拒绝接管未知浏览器", message)
            return False

        chrome_path = self.find_chrome_executable()
        if not chrome_path:
            message = "未找到 Chrome，请确认已安装 Google Chrome。"
            self.environment_status_label.setText("需要处理")
            self.refresh_dashboard_summary()
            self.append_log(f"[环境守护] {message}")
            if show_messages:
                QMessageBox.warning(self, "启动失败", message)
            return False

        ensure_runtime_dirs()
        os.makedirs(CHROME_PROFILE_DIR, exist_ok=True)
        self.cdp_port = find_free_tcp_port()
        self.cdp_endpoint = cdp_endpoint(self.cdp_port)
        args = [
            chrome_path,
            f"--remote-debugging-port={self.cdp_port}",
            f"--remote-debugging-address={DEFAULT_CDP_HOST}",
            f"--user-data-dir={CHROME_PROFILE_DIR}",
        ]
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(
            subprocess,
            "DETACHED_PROCESS",
            0,
        )
        try:
            process = subprocess.Popen(
                args,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creation_flags,
            )
            self.owned_chrome_pid = process.pid
            self.save_chrome_session()
        except Exception as exc:
            message = f"启动 Chrome 失败：{exc}"
            self.environment_status_label.setText("需要处理")
            self.refresh_dashboard_summary()
            self.append_log(f"[环境守护] {message}")
            if show_messages:
                QMessageBox.warning(self, "启动失败", message)
            return False

        self.append_log(f"[环境守护] 已启动可接管 Chrome，正在等待动态端口 {self.cdp_port}...")
        for _ in range(16):
            QApplication.processEvents()
            time.sleep(0.5)
            endpoint = self.current_cdp_endpoint()
            if endpoint:
                self.environment_status_label.setText("环境正常")
                self.refresh_dashboard_summary()
                self.append_log(f"[环境守护] 本软件 Chrome 调试端口已可用：{endpoint}")
                if show_messages:
                    QMessageBox.information(
                        self,
                        "Chrome 已启动",
                        "Chrome 已用本软件专属调试端口启动。请在该窗口确认闲鱼已登录。",
                    )
                return True

        message = "Chrome 已尝试启动，但本软件调试端口暂未响应。请稍等后点“检查环境”。"
        self.environment_status_label.setText("需要处理")
        self.refresh_dashboard_summary()
        self.append_log(f"[环境守护] {message}")
        if show_messages:
            QMessageBox.warning(self, "端口未就绪", message)
        return False

    def chrome_cache_targets(self):
        return chrome_cache_targets(CHROME_PROFILE_DIR)

    def clear_chrome_cache(self):
        if self.worker:
            QMessageBox.information(self, "提示", "请先停止监测，再清理浏览器缓存。")
            return

        removed_count, failed_paths = remove_chrome_cache(CHROME_PROFILE_DIR)
        if failed_paths:
            self.append_log("[缓存清理] 部分缓存未能删除：" + "；".join(failed_paths[:3]))
            QMessageBox.warning(
                self,
                "清理未完全完成",
                "部分缓存正在被 Chrome 占用。请关闭可接管 Chrome 后再试。",
            )
            return

        self.append_log(f"[缓存清理] 已清理 {removed_count} 个浏览器缓存目录，登录信息已保留。")
        QMessageBox.information(
            self,
            "清理完成",
            f"已清理 {removed_count} 个缓存目录。登录信息、Cookie 和历史配置已保留。",
        )

    def stop_owned_chrome(self):
        if not self.owned_chrome_pid:
            return
        ok, message = terminate_owned_chrome(self.owned_chrome_pid, CHROME_PROFILE_DIR)
        if ok:
            self.append_log("[环境守护] 已关闭本窗口启动的可接管 Chrome。")
        elif message and "已跳过" not in message:
            self.append_log(f"[环境守护] 关闭可接管 Chrome 失败：{message}")
        self.owned_chrome_pid = None
        self.cdp_port = None
        self.cdp_endpoint = None
        self.clear_chrome_session()

    def clear_results(self):
        self.found_items.clear()
        self.comparison_items.clear()
        self.price_suggestion_items.clear()
        self.result_table.setRowCount(0)
        self.comparison_table.setRowCount(0)
        self.price_suggestion_table.setRowCount(0)
        self.apply_result_filter()
        self.save_hit_history_now()
        self.append_log("[历史命中] 已清空当前显示的命中结果。")
        self.refresh_dashboard_summary()

    def mark_selected_result_viewed(self):
        self.set_selected_result_status("已查看")

    def mark_selected_result_contacted(self):
        self.set_selected_result_status("已联系")

    def mark_selected_result_ignored(self):
        self.set_selected_result_status("忽略")

    def mark_selected_result_favorite(self):
        self.set_selected_result_status("收藏")

    def export_log_text(
        self,
        log_text,
        file_prefix,
        success_title,
        empty_message,
        show_message=True,
    ):
        if not log_text:
            if show_message:
                QMessageBox.information(self, "提示", empty_message)
            return None

        file_name = f"{file_prefix}_{time.strftime('%Y%m%d_%H%M%S')}.txt"
        file_path = os.path.abspath(file_name)
        try:
            safe_log_text = "\n".join(
                redact_sensitive_text(line, title_limit=500)
                for line in log_text.splitlines()
            )
            atomic_write_text(file_path, safe_log_text)
            self.append_log(f"[操作] 已导出{success_title}：{file_path}")
            if show_message:
                QMessageBox.information(
                    self,
                    "导出成功",
                    f"{success_title}已导出：\n{file_path}",
                )
            return file_path
        except Exception as exc:
            if show_message:
                QMessageBox.warning(self, "导出失败", f"导出{success_title}失败：{exc}")
            return None

    def export_diagnostic_log(self):
        self.export_log_text(
            self.important_log_output.toPlainText().strip(),
            "important_diagnostic_log",
            "重要诊断日志",
            "当前没有可导出的重要日志。",
        )

    def export_full_diagnostic_log(self):
        self.export_log_text(
            self.log_output.toPlainText().strip(),
            "full_diagnostic_log",
            "完整诊断日志",
            "当前没有可导出的完整日志。",
        )

    def clear_database(self):
        answer = QMessageBox.question(
            self,
            "确认清空",
            "清空去重记录后，已经通知过的商品会在下一轮重新触发命中。确定清空吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            atomic_write_json(DB_FILE, [])
            if self.worker:
                self.worker.clear_scanned_items()
            self.append_log("[操作] 已清空 scanned_items.json 去重记录。")
        except Exception as exc:
            QMessageBox.warning(self, "清空失败", f"清空去重记录失败：{exc}")

    def persist_smart_rules(self):
        try:
            save_smart_rules(self.smart_rules)
        except Exception as exc:
            QMessageBox.warning(self, "学习失败", f"保存学习规则失败：{exc}")
            return False

        if self.worker:
            self.worker.smart_rules = self.smart_rules
        return True

    def mark_selected_result_bad(self):
        row, item = self.selected_found_item()
        if item is None:
            return

        title = item["title"]
        phrases = extract_bad_learning_phrases(title)
        self.smart_rules["blocked_titles"].append(title)
        self.smart_rules["blocked_phrases"].extend(phrases)
        self.smart_rules["feedback"].append(
            {
                "type": "bad",
                "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "keyword": item.get("keyword", ""),
                "title": title,
                "url": item.get("url", ""),
                "learned_phrases": phrases,
            }
        )
        if not self.persist_smart_rules():
            return

        self.set_item_status(item, "忽略")
        item_index = self.found_items.index(item)
        self.result_table.removeRow(row)
        self.found_items.pop(item_index)
        self.refresh_result_row_indexes()
        self.apply_result_sort_and_filter()
        self.save_hit_history_now()
        learned_text = "、".join(phrases) if phrases else "完整标题"
        self.append_log(f"[学习] 已标记误报，以后自动排除：{learned_text}")

    def mark_selected_result_good(self):
        _row, item = self.selected_found_item()
        if item is None:
            return

        title = item["title"]
        phrases = extract_good_learning_phrases(title)
        if not phrases:
            QMessageBox.information(
                self,
                "暂未学习",
                "这条标题里没有提取到稳定的好货特征，暂时不写入偏好规则。",
            )
            return

        self.smart_rules["preferred_phrases"].extend(phrases)
        self.smart_rules["feedback"].append(
            {
                "type": "good",
                "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "keyword": item.get("keyword", ""),
                "title": title,
                "url": item.get("url", ""),
                "learned_phrases": phrases,
            }
        )
        if not self.persist_smart_rules():
            return
        self.set_item_status(item, "收藏")
        row = self.result_row_for_item_index(self.found_items.index(item))
        if row is not None:
            self.result_table.setItem(row, 1, self.make_table_item("收藏"))
        self.apply_result_sort_and_filter()
        row = self.result_row_for_item_index(self.found_items.index(item))
        self.update_result_detail(item, row)
        self.save_hit_history_now()
        self.append_log(f"[学习] 已标记好货，以后相似结果会提高评分：{'、'.join(phrases)}")

    def clear_smart_rules(self):
        answer = QMessageBox.question(
            self,
            "确认清空",
            "清空学习规则后，标记误报/好货积累的偏好会失效。确定清空吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        self.smart_rules = empty_smart_rules()
        if not self.persist_smart_rules():
            return
        self.append_log("[操作] 已清空 smart_rules.json 学习规则。")

    def start_monitoring(self):
        try:
            config = self.build_config()
            platforms = self.build_platforms()
        except ValueError as exc:
            QMessageBox.warning(self, "配置错误", str(exc))
            return

        try:
            self.check_database_file()
        except Exception as exc:
            QMessageBox.warning(self, "环境错误", f"去重文件不可用：{exc}")
            return

        if not self.current_cdp_endpoint():
            self.append_log("[环境守护] 未检测到本软件 Chrome，正在自动启动...")
            if not self.launch_chrome_debug_browser(show_messages=False):
                QMessageBox.warning(
                    self,
                    "Chrome 未就绪",
                    "未能自动启动可接管 Chrome。请点击“一键启动 Chrome”或查看日志。",
                )
                return

        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.smart_rules = load_smart_rules()
        self.worker_thread = QThread(self)
        self.worker = XianyuMonitorWorker(
            config=config,
            interval_min=self.interval_min_input.value(),
            interval_max=self.interval_max_input.value(),
            black_words=self.build_black_words(),
            smart_match=self.smart_match_checkbox.isChecked(),
            prefer_personal=self.personal_filter_checkbox.isChecked(),
            smart_rules=(
                self.smart_rules
                if self.smart_filter_checkbox.isChecked()
                else empty_smart_rules()
            ),
            min_alert_score=self.min_alert_score_input.value(),
            rule_options=self.build_rule_options(),
            platforms=platforms,
        )
        self.worker.moveToThread(self.worker_thread)

        self.worker_thread.started.connect(self.worker.run)
        self.worker.log_signal.connect(self.append_log)
        self.worker.error_signal.connect(self.append_error)
        self.worker.item_found_signal.connect(self.on_item_found)
        self.worker.comparison_signal.connect(self.on_comparison_ready)
        self.worker.finished_signal.connect(self.on_worker_finished)
        self.worker.finished_signal.connect(self.worker_thread.quit)
        self.worker.finished_signal.connect(self.worker.deleteLater)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)
        self.worker_thread.start()
        self.header_status_label.setText("监测中")
        self.header_status_label.setStyleSheet(
            "background: #dbeafe; color: #1d4ed8; border-radius: 4px; padding: 5px 10px;"
        )
        self.append_log("[DEBUG] 监测线程已启动。")

    def stop_monitoring(self):
        if self.worker:
            self.worker.stop()
        self.stop_button.setEnabled(False)
        self.header_status_label.setText("正在停止")
        self.header_status_label.setStyleSheet(
            "background: #fef3c7; color: #92400e; border-radius: 4px; padding: 5px 10px;"
        )

    def on_worker_finished(self):
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.worker = None
        self.worker_thread = None
        self.header_status_label.setText("待机")
        self.header_status_label.setStyleSheet(
            "background: #e6f4ea; color: #166534; border-radius: 4px; padding: 5px 10px;"
        )

    def closeEvent(self, event):
        if self.tray_icon and not self.force_exit:
            event.ignore()
            self.hide_to_tray()
            return

        self.settings_save_timer.stop()
        self.save_current_settings()
        if self.worker:
            self.worker.stop()
        if self.worker_thread and self.worker_thread.isRunning():
            self.worker_thread.quit()
            deadline = time.time() + 10
            while self.worker_thread.isRunning() and time.time() < deadline:
                QApplication.processEvents()
                self.worker_thread.wait(200)
            if self.worker_thread.isRunning():
                self.append_log("[退出] 监测线程仍在收尾，已放弃强制结束以避免状态损坏。")
        if self.tray_icon:
            self.tray_icon.hide()
        if hasattr(self, "wake_event_poller"):
            self.wake_event_poller.close()
        self.stop_owned_chrome()
        event.accept()




__all__ = ["MainWindow"]
