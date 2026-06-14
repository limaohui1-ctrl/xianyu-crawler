"""Launcher and UI smoke checks for the universal self-test."""

import os
import sys


def verify_launcher_layout(window):
    if "ACS 资料采集助手" not in window.windowTitle():
        raise AssertionError("窗口标题错误")
    if "闲鱼" in window.windowTitle() or "咸鱼" in window.windowTitle() or "通用网站采集中心" in window.windowTitle():
        raise AssertionError("通用入口不应展示旧产品名")

    source_only_launchers = ()  # .spec removed — source-only delivery for v1.3.1
    universal_launchers = (
        "启动ACS资料采集助手.bat",
        "start_acs_desktop.bat",
        "start_acs_desktop.py",
        "main.py",
    )
    if not getattr(sys, "frozen", False):
        universal_launchers = universal_launchers + source_only_launchers
    for launcher_name in universal_launchers:
        launcher_path = os.path.join(os.getcwd(), launcher_name)
        if not os.path.exists(launcher_path):
            raise AssertionError(f"通用产品入口文件缺失：{launcher_name}")
        with open(launcher_path, "r", encoding="utf-8", errors="ignore") as file_obj:
            launcher_text = file_obj.read()
        if launcher_name.startswith("启动") and "--xianyu" in launcher_text:
            raise AssertionError(f"启动器不应进入闲鱼兼容模式：{launcher_name}")

    # Shortcut checks skipped — source-only delivery, no .lnk files required

    # Legacy xianyu launchers have been archived to D:\ACS_Archive\
    # They should NOT exist in the project root or old directory
    legacy_launcher_names = (
        "启动闲鱼监测软件.bat",
        "启动闲鱼监测软件_无黑窗.vbs",
        "启动闲鱼监测软件_EXE版.vbs",
    )
    if not getattr(sys, "frozen", False):
        for legacy_launcher_name in legacy_launcher_names:
            root_legacy_path = os.path.join(os.getcwd(), legacy_launcher_name)
            if os.path.exists(root_legacy_path):
                raise AssertionError(f"根目录不应保留旧闲鱼入口，避免误点：{legacy_launcher_name}")
        # Legacy directory should also be gone
        legacy_entry_dir = os.path.join(os.getcwd(), "旧版闲鱼兼容入口")
        if os.path.isdir(legacy_entry_dir):
            raise AssertionError("旧版闲鱼兼容入口目录已归档，不应留在项目根目录")


def verify_home_tabs(window):
    tab_names = [window.tabs.tabText(index) for index in range(window.tabs.count())]
    if window.tabs.tabText(window.tabs.currentIndex()) != "一键采集":
        raise AssertionError("默认首页必须是普通人一键采集面板")
    for expected_tab in ("一键采集", "监控概览", "AI 抓取工作台", "批量采集", "模板库", "历史与监控"):
        if expected_tab not in tab_names:
            raise AssertionError(f"主界面分区缺失：{expected_tab}")
    hidden_expert_tabs = [
        window.tabs.tabText(index)
        for index in range(window.tabs.count())
        if window.tabs.tabText(index) in getattr(window, "expert_tab_names", []) and window.tabs.isTabVisible(index)
    ]
    if hidden_expert_tabs:
        raise AssertionError("专家功能默认不应显示在普通人首页")


def verify_simple_panel(window):
    for attr_name in (
        "simple_url_input",
        "simple_goal_input",
        "simple_start_button",
        "simple_stop_button",
        "simple_ai_suggest_button",
        "simple_contact_button",
        "simple_image_button",
        "simple_schedule_button",
        "simple_retry_button",
        "simple_retry_low_quality_button",
        "simple_apply_diagnosis_button",
        "simple_sample_verify_button",
        "simple_strategy_compare_button",
        "simple_retry_report_button",
        "simple_real_check_button",
        "simple_depth_combo",
        "simple_column_card_label",
        "simple_ai_provider_combo",
        "simple_ai_model_combo",
        "simple_ai_key_input",
        "simple_ai_save_button",
        "simple_ai_test_button",
        "simple_result_table",
        "simple_result_summary_label",
        "simple_retry_report_label",
        "simple_diagnosis_label",
        "simple_repair_plan_label",
        "simple_fix_pagination_button",
        "simple_fix_subpages_button",
        "simple_fix_login_button",
        "simple_fix_fields_button",
        "simple_sample_verify_label",
        "simple_strategy_compare_label",
        "simple_discovery_label",
        "simple_step_labels",
        "simple_recent_files_table",
        "simple_recent_records_table",
        "simple_open_recent_file_button",
        "simple_open_recent_folder_button",
        "simple_preview_title_label",
        "simple_preview_url_label",
        "simple_preview_counts_label",
        "simple_preview_body_output",
        "simple_field_table",
        "simple_field_status_label",
        "simple_column_table",
        "simple_column_delete_button",
        "simple_input_box",
        "simple_ai_box",
        "simple_recent_box",
        "simple_main_splitter",
    ):
        if not hasattr(window, attr_name):
            raise AssertionError(f"普通人一键采集面板缺少控件：{attr_name}")
