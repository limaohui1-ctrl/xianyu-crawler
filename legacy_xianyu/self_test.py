import csv


def _self_test_dir():
    return os.path.abspath(os.environ.get("XIANYU_MONITOR_SELF_TEST_DIR", "self_test_runtime"))


def _is_self_test_path(file_path):
    try:
        base = os.path.normcase(_self_test_dir())
        target = os.path.normcase(os.path.abspath(file_path))
        return target == base or target.startswith(base + os.sep)
    except Exception:
        return False


def _remove_self_test_file(file_path):
    if not _is_self_test_path(file_path):
        raise AssertionError(f"自检拒绝删除正式路径：{file_path}")
    if os.path.exists(file_path):
        os.remove(file_path)


def _self_test_file(name):
    os.makedirs(_self_test_dir(), exist_ok=True)
    return os.path.join(_self_test_dir(), name)


def run_self_test(app_module):
    globals().update(vars(app_module))
    from .ui import MainWindow
    from .worker import XianyuMonitorWorker

    globals()["MainWindow"] = MainWindow
    globals()["XianyuMonitorWorker"] = XianyuMonitorWorker
    _run_self_test()

def _run_self_test():
    if os.environ.get("XIANYU_MONITOR_SELF_TEST") != "1":
        raise AssertionError("自检未进入隔离运行模式")
    _run_filter_self_test()
    for runtime_file in (
        APP_SETTINGS_FILE,
        HIT_HISTORY_FILE,
        APP_LOG_FILE,
        SMART_RULES_FILE,
        ITEM_STATUS_FILE,
        DB_FILE,
        CHROME_SESSION_FILE,
    ):
        _remove_self_test_file(runtime_file)
    print("[DEBUG] self-test: creating QApplication")
    app = QApplication(sys.argv)
    print("[DEBUG] self-test: creating MainWindow")
    window = MainWindow()
    print("[DEBUG] self-test: window title =", window.windowTitle())
    if not _is_self_test_path(DATA_DIR):
        raise AssertionError("自检运行数据目录未隔离")
    for runtime_file in (
        APP_SETTINGS_FILE,
        HIT_HISTORY_FILE,
        APP_LOG_FILE,
        SMART_RULES_FILE,
        ITEM_STATUS_FILE,
        DB_FILE,
        CHROME_PROFILE_DIR,
        CHROME_SESSION_FILE,
    ):
        if not _is_self_test_path(runtime_file):
            raise AssertionError(f"运行路径未进入自检目录：{runtime_file}")
    if CHROME_PROFILE_DIR == r"D:\咸鱼爬取软件\chrome-profile":
        raise AssertionError("Chrome profile 仍硬编码到项目目录")
    if window.min_alert_score_input.value() != 55:
        raise AssertionError("最低提醒评分默认值错误")
    if not all(window.build_rule_options().values()):
        raise AssertionError("规则中心默认开关错误")
    if window.environment_status_label.text() != "尚未检查":
        raise AssertionError("环境守护初始状态错误")
    if window.check_dependencies():
        raise AssertionError("运行环境依赖检查失败")
    if "win10toast" in sys.modules:
        raise AssertionError("通知库不应在自检阶段被主程序直接导入")
    if window.result_table.columnCount() != 11:
        raise AssertionError("命中结果状态列未创建")
    if not hasattr(window, "result_search_input"):
        raise AssertionError("命中结果搜索框未创建")
    if not hasattr(window, "result_status_filter"):
        raise AssertionError("命中结果状态筛选未创建")
    if not hasattr(window, "result_toolbox") or window.result_toolbox.count() < 4:
        raise AssertionError("结果页折叠面板未创建")
    if not hasattr(window, "important_log_output") or not hasattr(window, "log_tabs"):
        raise AssertionError("日志分级视图未创建")
    if not hasattr(window, "export_full_log_button"):
        raise AssertionError("完整日志导出按钮未创建")
    if window.minimumWidth() > 760 or window.sidebar_scroll.minimumWidth() > 240:
        raise AssertionError("缩小窗口布局限制过宽")
    if window.comparison_table.columnCount() != 7:
        raise AssertionError("平台比价表未创建")
    if window.price_suggestion_table.columnCount() != 6:
        raise AssertionError("智能价格建议表未创建")
    if not hasattr(window, "apply_latest_price_suggestion_button"):
        raise AssertionError("一键应用最新价格建议按钮未创建")
    if not hasattr(window, "clear_cache_button"):
        raise AssertionError("浏览器缓存清理按钮未创建")
    if not hasattr(window, "refresh_process_button"):
        raise AssertionError("后台进程刷新按钮未创建")
    if not hasattr(window, "stop_other_processes_button"):
        raise AssertionError("结束其他实例按钮未创建")
    if window.process_status_label.text() == "尚未检查":
        raise AssertionError("后台进程状态未初始化")
    if not hasattr(window, "tray_icon") or not hasattr(window, "quit_from_tray"):
        raise AssertionError("托盘功能未初始化")
    if window.force_exit:
        raise AssertionError("托盘退出标志默认值错误")
    cache_target_names = " ".join(window.chrome_cache_targets()).lower()
    if "cache" not in cache_target_names or "crashpad" not in cache_target_names:
        raise AssertionError("浏览器缓存清理目标不完整")
    if window.build_platforms() != ["xianyu"]:
        raise AssertionError("默认平台选择错误")
    settings_test_file = _self_test_file("app_settings_self_test.json")
    try:
        saved_settings = window.current_settings()
        save_app_settings(saved_settings, settings_test_file)
        loaded_settings = load_app_settings(settings_test_file)
        if loaded_settings.get("monitor_rows") != saved_settings.get("monitor_rows"):
            raise AssertionError("配置保存/读取失败")
        window.interval_min_input.setValue(240)
        window.platform_jd_checkbox.setChecked(True)
        save_app_settings(window.current_settings(), settings_test_file)
        reloaded_settings = load_app_settings(settings_test_file)
        if reloaded_settings.get("interval_min") != 240:
            raise AssertionError("配置变更保存失败")
        if not reloaded_settings.get("platforms", {}).get("jd"):
            raise AssertionError("平台配置保存失败")
    finally:
        if os.path.exists(settings_test_file):
            _remove_self_test_file(settings_test_file)
    fake_comparison = {
        "keyword": "Mac mini M4",
        "platforms": {
            "taobao": {
                "platform_name": "淘宝",
                "price": 4699,
                "title": "Mac mini M4 24GB",
                "url": "https://item.taobao.com/item.htm?id=test",
                "in_alert_range": False,
            }
        },
        "best_platform_name": "淘宝",
        "best_url": "https://item.taobao.com/item.htm?id=test",
        "price_suggestion": {
            "keyword": "Mac mini M4",
            "current_min_price": 2500,
            "current_max_price": 3500,
            "suggested_min_price": 2500,
            "suggested_max_price": 5000,
            "best_price": 4699,
            "platform_name": "淘宝",
            "action": "raise_max",
            "reason": "测试建议",
        },
    }
    window.on_comparison_ready(fake_comparison)
    if window.price_suggestion_table.rowCount() != 1:
        raise AssertionError("智能价格建议未显示")
    window.apply_latest_price_suggestion()
    if window.config_table.item(0, 2).text() != "5000":
        raise AssertionError("一键应用最新价格建议未写回配置表")
    if window.price_suggestion_table.rowCount() != 0:
        raise AssertionError("一键应用最新价格建议后未移除建议")
    fake_hit = {
        "platform_name": "闲鱼",
        "keyword": "Mac mini M4",
        "page_number": 1,
        "price": 3200,
        "score": 88,
        "level": "高",
        "quality_reason": "测试命中",
        "title": "Mac mini M4 自用闲置",
        "url": "https://www.goofish.com/item?id=history-test",
    }
    window.on_item_found(fake_hit)
    second_fake_hit = dict(fake_hit)
    second_fake_hit.update(
        {
            "keyword": "Xeon E5 2696 V4",
            "title": "Xeon E5 2696 V4 CPU 正式版",
            "url": "https://www.goofish.com/item?id=history-test-2",
        }
    )
    window.on_item_found(second_fake_hit)
    cross_title_fake_hit = dict(fake_hit)
    cross_title_fake_hit.update(
        {
            "keyword": "Mac mini M4",
            "title": "Mac mini M4 可换 Xeon E5 2696 V4",
            "url": "https://www.goofish.com/item?id=history-test-3",
            "price": 3300,
        }
    )
    window.on_item_found(cross_title_fake_hit)
    if not hasattr(window, "result_detail_title_label"):
        raise AssertionError("命中结果详情面板未创建")
    xeon_row = window.result_row_for_item_index(1)
    if xeon_row is None:
        raise AssertionError("未找到 Xeon 命中结果行")
    window.result_table.selectRow(xeon_row)
    window.update_result_detail_from_selection()
    if "Xeon E5 2696 V4 CPU 正式版" not in window.result_detail_title_label.text():
        raise AssertionError("命中结果详情面板未同步选中结果")
    window.mark_selected_result_favorite()
    if "收藏" not in window.result_detail_status_label.text():
        raise AssertionError("命中结果详情状态未同步更新")
    window.result_sort_combo.setCurrentText("按价格最低")
    window.apply_result_sort_and_filter()
    first_visible = window.visible_result_items()[0]
    if first_visible.get("price") != 3200:
        raise AssertionError("命中结果价格排序失败")
    window.only_favorites_button.setChecked(True)
    favorite_items = window.visible_result_items()
    if len(favorite_items) != 1 or favorite_items[0].get("keyword") != "Xeon E5 2696 V4":
        raise AssertionError("一键只看收藏筛选失败")
    if "Xeon E5 2696 V4 CPU 正式版" not in window.result_detail_title_label.text():
        raise AssertionError("收藏筛选后详情面板指向错误")
    window.only_favorites_button.setChecked(False)
    window.result_sort_combo.setCurrentText("按时间最新")
    window.result_group_type_combo.setCurrentText("按关键词")
    window.update_result_groups()
    if window.result_group_table.rowCount() < 2:
        raise AssertionError("命中结果分组统计未生成")
    group_names = [
        window.result_group_table.item(row, 0).text()
        for row in range(window.result_group_table.rowCount())
    ]
    if "Mac mini M4" not in group_names or "Xeon E5 2696 V4" not in group_names:
        raise AssertionError("命中结果关键词分组错误")
    xeon_group_row = group_names.index("Xeon E5 2696 V4")
    window.apply_result_group_filter(xeon_group_row, 0)
    if len(window.visible_result_items()) != 1:
        raise AssertionError("双击分组筛选失败")
    window.clear_result_filters()
    if len(window.visible_result_items()) != 3:
        raise AssertionError("清除结果筛选失败")
    window.result_search_input.setText("Mac")
    if not window.batch_set_visible_status("已查看"):
        raise AssertionError("批量标记可见结果失败")
    mac_items = [
        item for item in window.found_items if item.get("keyword") == "Mac mini M4"
    ]
    if len(mac_items) != 2 or any(item.get("status") != "已查看" for item in mac_items):
        raise AssertionError("批量标记未写回内部结果")
    window.clear_result_filters()
    window.result_search_input.setText("CPU 正式版")
    window.apply_result_filter()
    visible_after_search = window.visible_result_items()
    if (
        len(visible_after_search) != 1
        or visible_after_search[0].get("keyword") != "Xeon E5 2696 V4"
    ):
        raise AssertionError("命中结果搜索筛选失败")
    window.result_search_input.clear()
    window.result_status_filter.setCurrentText("已查看")
    window.apply_result_filter()
    visible_after_status = window.visible_result_items()
    if (
        len(visible_after_status) != 2
        or any(item.get("keyword") != "Mac mini M4" for item in visible_after_status)
    ):
        raise AssertionError("命中结果状态筛选失败")
    window.result_status_filter.setCurrentText("全部状态")
    export_test_file = _self_test_file("命中结果_self_test.csv")
    try:
        window.result_search_input.setText("CPU 正式版")
        visible_items = window.visible_result_items()
        if len(visible_items) != 1 or visible_items[0].get("keyword") != "Xeon E5 2696 V4":
            raise AssertionError("导出前筛选结果错误")
        window.export_results_to_file(export_test_file, visible_items)
        with open(export_test_file, "r", encoding="utf-8-sig", newline="") as f:
            rows = list(csv.reader(f))
        if rows[0] != window.result_export_headers():
            raise AssertionError("命中结果导出表头错误")
        if len(rows) != 2 or "Xeon E5 2696 V4" not in rows[1]:
            raise AssertionError("命中结果导出内容错误")
    finally:
        window.result_search_input.clear()
        if os.path.exists(export_test_file):
            _remove_self_test_file(export_test_file)
    xlsx_export_test_file = _self_test_file("命中结果_self_test.xlsx")
    try:
        window.export_results_to_file(xlsx_export_test_file, window.visible_result_items())
        if not os.path.exists(xlsx_export_test_file):
            raise AssertionError("Excel 导出文件未生成")
    finally:
        if os.path.exists(xlsx_export_test_file):
            _remove_self_test_file(xlsx_export_test_file)
    atomic_write_json(
        CHROME_SESSION_FILE,
        {
            "pid": 0,
            "port": 9222,
            "endpoint": "http://127.0.0.1:9222",
            "profile_dir": CHROME_PROFILE_DIR,
        },
    )
    if window.current_cdp_endpoint():
        raise AssertionError("无效 Chrome 会话不应被信任")
    _remove_self_test_file(CHROME_SESSION_FILE)
    window.append_log("排除低质量结果：命中排除词「全新」 | 测试商品")
    window.append_log("排除求购/回收结果：测试求购标题")
    window.append_log("正在刷新数据...")
    window.append_log("正在监测商品：Mac mini M4，价格 2500-3500 元，扫描 1 页")
    window.flush_log_noise_summary()
    if "[日志降噪]" not in window.log_output.toPlainText():
        raise AssertionError("日志降噪摘要未输出")
    if "正在刷新数据" in window.important_log_output.toPlainText():
        raise AssertionError("普通扫描过程日志不应进入重要日志")
    if "[日志降噪]" not in window.important_log_output.toPlainText():
        raise AssertionError("日志降噪摘要未进入重要日志")
    important_log_file = None
    full_log_file = None
    try:
        for name in os.listdir(_self_test_dir()):
            if name.startswith("important_diagnostic_self_test_") or name.startswith("full_diagnostic_self_test_"):
                _remove_self_test_file(os.path.join(_self_test_dir(), name))
        important_log_file = window.export_log_text(
            window.important_log_output.toPlainText().strip(),
            _self_test_file("important_diagnostic_self_test"),
            "重要诊断日志",
            "当前没有可导出的重要日志。",
            show_message=False,
        )
        full_log_file = window.export_log_text(
            window.log_output.toPlainText().strip(),
            _self_test_file("full_diagnostic_self_test"),
            "完整诊断日志",
            "当前没有可导出的完整日志。",
            show_message=False,
        )
        if not important_log_file or not full_log_file:
            raise AssertionError("诊断日志导出文件未生成")
        with open(important_log_file, "r", encoding="utf-8") as f:
            important_export = f.read()
        with open(full_log_file, "r", encoding="utf-8") as f:
            full_export = f.read()
        if "正在刷新数据" in important_export:
            raise AssertionError("重要诊断日志不应导出普通过程日志")
        if "正在刷新数据" not in full_export:
            raise AssertionError("完整诊断日志应保留普通过程日志")
    finally:
        for path in (important_log_file, full_log_file):
            if path and os.path.exists(path):
                _remove_self_test_file(path)
    simulated_hits = [
        {
            "platform_name": "闲鱼",
            "keyword": "模拟商品A",
            "page_number": 1,
            "price": 100 + index,
            "score": 70 + index,
            "level": "模拟",
            "quality_reason": "模拟扫描命中",
            "title": f"模拟扫描商品 {index}",
            "url": f"https://www.goofish.com/item?id=simulated-{index}",
        }
        for index in range(3)
    ]
    for hit in simulated_hits:
        window.on_item_found(hit)
    window.result_search_input.setText("模拟商品A")
    if len(window.visible_result_items()) != 3:
        raise AssertionError("模拟扫描结果筛选失败")
    window.result_sort_combo.setCurrentText("按评分最高")
    if window.visible_result_items()[0].get("score") != 72:
        raise AssertionError("模拟扫描结果排序失败")
    window.clear_result_filters()
    saved_hits = load_hit_history()
    if not saved_hits or saved_hits[-1].get("url") != "https://www.goofish.com/item?id=simulated-2":
        raise AssertionError("历史命中保存失败")
    if not os.path.exists(APP_LOG_FILE):
        raise AssertionError("监测日志未写入文件")
    window.clear_results()
    if load_hit_history():
        raise AssertionError("清空结果后历史命中未同步清空")
    for runtime_file in (
        APP_SETTINGS_FILE,
        HIT_HISTORY_FILE,
        APP_LOG_FILE,
        SMART_RULES_FILE,
        ITEM_STATUS_FILE,
    ):
        if os.path.exists(runtime_file):
            _remove_self_test_file(runtime_file)
        archive_file = f"{runtime_file}.archive.json"
        if os.path.exists(archive_file):
            _remove_self_test_file(archive_file)
    print("[DEBUG] self-test: OK")
    app.quit()


def _run_filter_self_test():
    class SilentToaster:
        def show_toast(self, *args, **kwargs):
            return None

    worker = XianyuMonitorWorker([], 60, 90)
    buyer_titles = [
        "教育优惠补贴Mac mini m4，淘宝京东的货都可以，28 00收。要求带票，功能完好无维修，有开机视频，未激活或激活六个月内。256g以上硬盘容量，诚心卖的联系。",
        "几乎全新Mac mini M4，16G+256G，银色主机，M4芯片 价格好聊，有机器的人联系我，细节私聊～ 我买哦，看清楚，我要一个",
    ]
    seller_title = (
        "出Mac mini M4芯片主机 16G+256G 25年3月购买，没用几次自用闲置，"
        "成色几乎全新，外观很新，没磕碰划痕，功能正常，无拆修带原装电源线，配件齐全仅支持自提"
    )

    missed_titles = [
        title for title in buyer_titles if not worker.buyer_intent_match(title)
    ]
    if missed_titles:
        raise AssertionError(f"求购过滤自检失败：{missed_titles[0]}")

    if worker.buyer_intent_match(seller_title):
        raise AssertionError(f"正常卖家标题被误判：{seller_title}")

    cpu_board_title = (
        "#x99ED4(H55芯片组) 芯片组与CPU插槽：采用Intel X99芯片组，"
        "支持双路LGA2011-V3插槽，可安装两颗Xeon E5系列处理器，如E5-2678或E5-2696 v4等"
    )
    cpu_seller_title = "Intel Xeon E5 2696 V4 CPU 正式版 散片 单颗 包正常使用"
    if not worker.product_type_mismatch_match(cpu_board_title, "Xeon E5 2696 V4"):
        raise AssertionError("X99 主板兼容说明未被识别为类型不匹配")

    if worker.product_type_mismatch_match(cpu_seller_title, "Xeon E5 2696 V4"):
        raise AssertionError("正常 CPU 标题被误判为类型不匹配")

    cpu_supported_board_title = (
        "个人闲置 Intel Xeon E5-2696V4 CPU，22核44线程，2.20GHz，"
        "LGA2011-3接口，支持X99主板。从服务器上拆下，成色几乎全新"
    )
    if worker.product_type_mismatch_match(cpu_supported_board_title, "Xeon E5 2696 V4"):
        raise AssertionError("CPU 本体因支持 X99 主板描述被误判")

    merchant_mac_title = (
        "#Apple/苹果 苹果 Mac mini M4主机，国行全新24款，16G+512G，"
        "品质：国行正品，专卖店直供，全新未激活，官方质检，假一赔三，欢迎咨询"
    )
    if not any(word in merchant_mac_title for word in DEFAULT_BLACK_WORDS):
        raise AssertionError("商家式 Mac mini 文案未被默认过滤词覆盖")

    private_mac_title = (
        "砍价绕道！Mac mini M4芯片主机，16G+256，国行正品，已过保，"
        "带原包装盒，无拆修，配件齐全，电源线都在"
    )
    if any(word in private_mac_title for word in DEFAULT_BLACK_WORDS):
        raise AssertionError("国行正品个人卖家标题被硬过滤误伤")
    if worker.product_type_mismatch_match(private_mac_title, "Mac mini M4"):
        raise AssertionError("带电源线的 Mac mini 本体被误判为配件")

    no_repair_mac_title = (
        "Mac mini M4 16G+256G 在保还有半年，自用一手产品，"
        "无任何维修记录，主机成色新，功能正常"
    )
    if worker.product_type_mismatch_match(no_repair_mac_title, "Mac mini M4"):
        raise AssertionError("无维修记录的 Mac mini 本体被误判为维修服务")

    bundle_mac_title = (
        "个人闲置｜Mac mini M4+红米4K显示器 整套打包出 自用闲置全套，"
        "配置清单苹果Mac mini M4主机官方标配"
    )
    if not worker.product_type_mismatch_match(bundle_mac_title, "Mac mini M4"):
        raise AssertionError("Mac mini 显示器套装未被识别为类型不匹配")

    smart_rules = empty_smart_rules()
    smart_rules["blocked_phrases"] = ["有机器的人联系我"]
    smart_rules["preferred_phrases"] = ["自用", "闲置"]
    learning_worker = XianyuMonitorWorker([], 60, 90, smart_rules=smart_rules)
    if not learning_worker.learned_block_match(buyer_titles[1]):
        raise AssertionError("学习误报规则未生效")

    _score, _level, reason = learning_worker.evaluate_item_quality(
        seller_title,
        3200,
        2500,
        3500,
    )
    if "符合你的偏好" not in reason:
        raise AssertionError("学习偏好评分未生效")

    recommendation_stats = worker.empty_scan_stats()
    recommendation_stats.update(
        {
            "candidate_count": 150,
            "new_count": 150,
            "hit_count": 1,
            "skipped_keyword": 120,
            "skipped_type_mismatch": 3,
            "max_hit_page": 1,
        }
    )
    recommendations = worker.build_monitor_recommendations(
        {
            "keyword": "Xeon E5 2696 V4",
            "min_price": 100,
            "max_price": 200,
            "pages": 5,
        },
        recommendation_stats,
    )
    recommendation_text = " ".join(recommendations)
    if "关键词" not in recommendation_text or "扫描页数" not in recommendation_text:
        raise AssertionError("智能推荐参数自检失败")
    if "CPU、处理器" not in recommendation_text or "CPU、处理器、主机" in recommendation_text:
        raise AssertionError("CPU 关键词建议不够精准")

    single_page_stats = worker.empty_scan_stats()
    single_page_stats.update(
        {
            "candidate_count": 30,
            "new_count": 29,
            "hit_count": 5,
            "skipped_price": 22,
            "skipped_price_high": 22,
            "max_hit_page": 1,
        }
    )
    single_page_recommendations = worker.build_monitor_recommendations(
        {
            "keyword": "Mac mini M4",
            "min_price": 2500,
            "max_price": 3500,
            "pages": 1,
        },
        single_page_stats,
    )
    single_page_text = " ".join(single_page_recommendations)
    if "最后一页仍有命中" in single_page_text or "当前扫描 1 页" not in single_page_text:
        raise AssertionError("单页扫描建议仍然过于机械")

    low_score_worker = XianyuMonitorWorker([], 60, 90, min_alert_score=55)
    low_score_worker._running = True
    low_score_html = """
    <a href="https://www.goofish.com/item?id=low-score-test">
        <div class="title">macmini M4 16+256 成色如图 过保 正常使用箱说全 顺丰到付 不退不换</div>
        <span>¥</span><span>3499</span>
    </a>
    """
    low_score_stats = low_score_worker.parse_and_check(
        low_score_html,
        {
            "keyword": "Mac mini M4",
            "min_price": 2500,
            "max_price": 3500,
            "pages": 1,
        },
    )
    if low_score_stats["hit_count"] != 0 or low_score_stats["skipped_low_score"] != 1:
        raise AssertionError("低分结果未被最低提醒评分拦截")

    attribute_price_worker = XianyuMonitorWorker([], 60, 90)
    attribute_price_worker.toaster = SilentToaster()
    attribute_price_worker._running = True
    attribute_price_html = """
    <a href="https://www.goofish.com/item?id=attr-price-test" title="Mac mini M4 16G 256G 自用闲置">
        <span class="price" aria-label="价格 3200元"></span>
    </a>
    """
    attribute_price_stats = attribute_price_worker.parse_and_check(
        attribute_price_html,
        {
            "keyword": "Mac mini M4",
            "min_price": 2500,
            "max_price": 3500,
            "pages": 1,
        },
    )
    if attribute_price_stats["hit_count"] != 1 or attribute_price_stats["skipped_parse"] != 0:
        raise AssertionError("属性里的价格未被正确解析")

    stop_stats = attribute_price_worker.merge_scan_stats(
        attribute_price_worker.empty_scan_stats(),
        None,
    )
    if stop_stats["candidate_count"] != 0:
        raise AssertionError("停止扫描空统计合并异常")

    dedupe_worker = XianyuMonitorWorker([], 60, 90)
    dedupe_worker.toaster = SilentToaster()
    dedupe_worker._running = True
    price_later_html = """
    <a href="https://www.goofish.com/item?id=price-later">
        <div class="title">Mac mini M4 16G 256G 自用闲置 功能正常</div>
        <span>¥</span><span>3600</span>
    </a>
    """
    first_price_stats = dedupe_worker.parse_and_check(
        price_later_html,
        {
            "keyword": "Mac mini M4",
            "min_price": 2500,
            "max_price": 3500,
            "pages": 1,
        },
    )
    second_price_stats = dedupe_worker.parse_and_check(
        price_later_html,
        {
            "keyword": "Mac mini M4",
            "min_price": 2500,
            "max_price": 3700,
            "pages": 1,
        },
    )
    third_price_stats = dedupe_worker.parse_and_check(
        price_later_html,
        {
            "keyword": "Mac mini M4",
            "min_price": 2500,
            "max_price": 3700,
            "pages": 1,
        },
    )
    if (
        first_price_stats["hit_count"] != 0
        or first_price_stats["skipped_price"] != 1
        or second_price_stats["hit_count"] != 1
        or third_price_stats["skipped_seen"] != 1
    ):
        raise AssertionError("价格区间调整后的去重策略异常")

    platform_worker = XianyuMonitorWorker([], 60, 90, platforms=["xianyu", "jd", "taobao"])
    platform_worker.toaster = SilentToaster()
    platform_worker._running = True
    taobao_page_url = platform_worker.url_with_query_param(
        "https://s.taobao.com/search?page=1&q=Mac%20mini%20M4%2024GB&tab=all",
        "page",
        5,
    )
    if "page=5" not in taobao_page_url or "q=Mac+mini+M4+24GB" not in taobao_page_url:
        raise AssertionError("淘宝分页地址生成失败")
    taobao_corrected_page_url = platform_worker.url_with_query_param(
        "https://s.taobao.com/search?page=31&q=Mac%20mini%20M4&tab=all",
        "page",
        5,
    )
    if platform_worker.query_param_value(taobao_corrected_page_url, "page") != "5":
        raise AssertionError("淘宝异常页码纠正失败")

    jd_html = """
    <div class="plugin_goodsCardWrapper" data-sku="100012043978">
        <div class="title" title="Apple Mac mini M4 16G 256G 主机"></div>
        <span>¥</span><span>3999</span>
    </div>
    """
    jd_stats = platform_worker.parse_and_check(
        jd_html,
        {
            "keyword": "Mac mini M4",
            "min_price": 0,
            "max_price": 999999,
            "pages": 1,
            "_platform": "jd",
        },
    )
    if jd_stats["hit_count"] != 1 or jd_stats["hits"][0]["platform_name"] != "京东":
        raise AssertionError("京东平台解析自检失败")

    class FakeBlockedPage:
        url = "https://passport.jd.com/new/login.aspx"

        def title(self):
            return "京东-欢迎登录"

    jd_block_message = platform_worker.detect_login_or_verification_page(
        FakeBlockedPage(),
        "jd",
    )
    if not jd_block_message or "登录/验证页" not in jd_block_message:
        raise AssertionError("京东登录/验证页识别失败")
    platform_worker.handle_platform_risk_block("jd", jd_block_message)
    if platform_worker.platform_risk_cooldowns.get("jd") != 3:
        raise AssertionError("京东风控冷却轮数错误")
    if not platform_worker.consume_platform_risk_cooldown("jd"):
        raise AssertionError("京东风控冷却未生效")
    if platform_worker.platform_risk_cooldowns.get("jd") != 2:
        raise AssertionError("京东风控冷却消费失败")

    taobao_html = """
    <a id="item_id_888888" class="doubleCardWrapperAdapt--mEcC7olq" href="//item.taobao.com/item.htm?id=888888" title="Mac mini M4 16G 256G 苹果主机">
        <span>￥</span><span>3799</span>
    </a>
    """
    taobao_stats = platform_worker.parse_and_check(
        taobao_html,
        {
            "keyword": "Mac mini M4",
            "min_price": 0,
            "max_price": 999999,
            "pages": 1,
            "_platform": "taobao",
        },
    )
    if taobao_stats["hit_count"] != 1 or taobao_stats["hits"][0]["platform_name"] != "淘宝":
        raise AssertionError("淘宝平台解析自检失败")

    taobao_spec_html = """
    <a id="item_id_999999" class="doubleCardWrapperAdapt--mEcC7olq" href="//item.taobao.com/item.htm?id=999999" title="Apple Mac mini M4 主机">
        <span class="sku">24G 统一内存 512G 固态</span>
        <span>￥</span><span>4299</span>
    </a>
    """
    taobao_spec_stats = platform_worker.parse_and_check(
        taobao_spec_html,
        {
            "keyword": "Mac mini M4 24GB",
            "min_price": 2500,
            "max_price": 3500,
            "pages": 1,
            "_platform": "taobao",
        },
    )
    if (
        taobao_spec_stats["hit_count"] != 0
        or taobao_spec_stats["skipped_keyword"] != 0
        or taobao_spec_stats["skipped_price"] != 1
        or len(taobao_spec_stats["comparison_candidates"]) != 1
    ):
        raise AssertionError("淘宝规格词整卡匹配或超价比价候选自检失败")

    taobao_noise_html = """
    <div>
        <a id="item_id_noise_rent" class="doubleCardWrapperAdapt--mEcC7olq" href="//item.taobao.com/item.htm?id=noise1" title="mac M4租用苹果电脑远程出租赁MAC云电脑mini实体macos服务器体验">
            <span>￥</span><span>3</span>
        </a>
        <a id="item_id_noise_pro" class="doubleCardWrapperAdapt--mEcC7olq" href="//item.taobao.com/item.htm?id=noise2" title="Apple/苹果 Mac mini Apple M4 Pro 芯片 24GB 统一内存 512GB 固态硬盘">
            <span>￥</span><span>9499</span>
        </a>
        <a id="item_id_noise_studio" class="doubleCardWrapperAdapt--mEcC7olq" href="//item.taobao.com/item.htm?id=noise3" title="Apple/苹果 Mac Studio Apple M4 Max 芯片 36GB 统一内存 512GB 固态硬盘">
            <span>￥</span><span>16499</span>
        </a>
        <a id="item_id_noise_custom" class="doubleCardWrapperAdapt--mEcC7olq" href="//item.taobao.com/item.htm?id=noise4" title="苹果 Mac Mini M4 24G+2TB定制机,支持预装openclaw和DeepSeek">
            <span>￥</span><span>7899</span>
        </a>
        <a id="item_id_good_24gb" class="doubleCardWrapperAdapt--mEcC7olq" href="//item.taobao.com/item.htm?id=good1" title="Apple/苹果 Mac mini M4 芯片 24GB 统一内存 512GB 固态硬盘 迷你台式机">
            <span>￥</span><span>6374</span>
        </a>
    </div>
    """
    taobao_noise_stats = platform_worker.parse_and_check(
        taobao_noise_html,
        {
            "keyword": "Mac mini M4 24GB",
            "min_price": 2500,
            "max_price": 99999,
            "pages": 1,
            "_platform": "taobao",
        },
    )
    if (
        taobao_noise_stats["hit_count"] != 1
        or taobao_noise_stats["hits"][0]["item_id"] != "good1"
        or len(taobao_noise_stats["comparison_candidates"]) != 1
    ):
        raise AssertionError("淘宝服务/混合型号精准过滤自检失败")

    suspicious_comparison = platform_worker.build_price_comparison(
        {"keyword": "Mac mini M4", "min_price": 2500, "max_price": 4500},
        {
            "taobao": [
                {
                    "price": 9,
                    "title": "Mac mini M4 远程云电脑租用 1小时体验",
                    "url": "https://item.taobao.com/item.htm?id=bad",
                },
                {
                    "price": 3799,
                    "title": "Apple Mac mini M4 16G 256G 苹果主机",
                    "url": "https://item.taobao.com/item.htm?id=good",
                },
            ]
        },
    )
    if suspicious_comparison["best_price"] != 3799:
        raise AssertionError("异常低价或服务结果仍参与平台比价")

    comparison = platform_worker.build_price_comparison(
        {"keyword": "Mac mini M4", "min_price": 2500, "max_price": 4500},
        {
            "xianyu": [
                {
                    "price": 3500,
                    "title": "闲鱼 Mac mini M4",
                    "url": "https://www.goofish.com/item?id=1",
                }
            ],
            "jd": jd_stats["hits"],
            "taobao": taobao_stats["hits"],
        },
    )
    if comparison["best_platform"] != "xianyu" or comparison["price_gap"] != 299:
        raise AssertionError("三平台比价自检失败")

    over_range_comparison = platform_worker.build_price_comparison(
        {"keyword": "Mac mini M4 24GB", "min_price": 2500, "max_price": 3500},
        {"taobao": taobao_spec_stats["comparison_candidates"]},
    )
    if (
        over_range_comparison["best_platform"] != "taobao"
        or "高于提醒上限" not in over_range_comparison["summary"]
    ):
        raise AssertionError("超出提醒区间的平台比价自检失败")
    price_suggestion = over_range_comparison.get("price_suggestion")
    if not price_suggestion or price_suggestion["suggested_max_price"] != 4600:
        raise AssertionError("智能价格建议自检失败")

    merchant_power_bank = (
        "全新未拆封小米自带线充电宝10000口袋版，正品保证。"
        "包邮，喜欢直接拍，售出不退不换"
    )
    used_power_bank = (
        "几乎全新小米10000mAh充电宝，循环十来次，电池无老化，"
        "一直闲置在家，便宜卖了，无包装有充电线，价格可小刀"
    )
    merchant_score, _merchant_level, _merchant_reason = worker.evaluate_item_quality(
        merchant_power_bank,
        60,
        10,
        80,
    )
    used_score, _used_level, _used_reason = worker.evaluate_item_quality(
        used_power_bank,
        25,
        10,
        80,
    )
    if merchant_score >= 55:
        raise AssertionError("充电宝商家模板文案没有被压到最低提醒评分以下")
    if used_score < 70:
        raise AssertionError("个人闲置充电宝被过度降权")

    all_category_type_cases = [
        (
            "iPhone 15 Pro Max",
            "iPhone 15 Pro Max 手机壳 MagSafe 透明保护壳",
            True,
        ),
        (
            "iPhone 15 Pro Max",
            "个人自用 iPhone 15 Pro Max 256G 国行，电池健康 92，功能正常",
            False,
        ),
        (
            "索尼 A7C",
            "索尼 A7C 相机包 便携收纳包 防震保护",
            True,
        ),
        (
            "戴森吹风机",
            "戴森吹风机支架 免打孔收纳架",
            True,
        ),
        (
            "MacBook Pro 14",
            "MacBook Pro 14 原装包装盒 空盒 仅盒子",
            True,
        ),
        (
            "充电宝",
            "个人闲置小米充电宝 10000mAh，循环十来次，功能正常",
            False,
        ),
        (
            "苹果电脑",
            "苹果一体机 iMac 模型机，不具备任何实际使用功能",
            True,
        ),
        (
            "组装电脑",
            "写配置单 台式电脑主机 组装电脑 配置咨询 装机服务",
            True,
        ),
        (
            "组装电脑",
            "可以帮忙组装电脑，装系统，不是卖电脑！！！",
            True,
        ),
        (
            "咖啡豆",
            "【出】三角洲行动 高级咖啡豆 手游端游虚拟道具 游戏内交易",
            True,
        ),
        (
            "咖啡豆",
            "高级咖啡豆，支持手机跟车扫码代撞，包到仓库，不进仓库不收钱",
            True,
        ),
        (
            "咖啡豆",
            "出咖啡豆，自己烘的，有证，小锅烘的，实在喝不完",
            False,
        ),
    ]
    for keyword, title, should_mismatch in all_category_type_cases:
        mismatch = worker.product_type_mismatch_match(title, keyword)
        if should_mismatch and not mismatch:
            raise AssertionError(f"全类目自检失败，未识别非本体：{keyword} | {title}")
        if not should_mismatch and mismatch:
            raise AssertionError(f"全类目自检失败，商品本体被误判：{keyword} | {title}")

    accessory_off_worker = XianyuMonitorWorker(
        [],
        60,
        90,
        rule_options={"filter_accessories": False},
    )
    if accessory_off_worker.product_type_mismatch_match(
        "iPhone 15 Pro Max 手机壳 MagSafe 透明保护壳",
        "iPhone 15 Pro Max",
    ):
        raise AssertionError("关闭过滤配件后仍然拦截配件")

    merchant_penalty_off_worker = XianyuMonitorWorker(
        [],
        60,
        90,
        rule_options={"merchant_penalty": False},
    )
    merchant_score_with_penalty = worker.evaluate_item_quality(
        merchant_power_bank,
        60,
        10,
        80,
    )[0]
    merchant_score_without_penalty = merchant_penalty_off_worker.evaluate_item_quality(
        merchant_power_bank,
        60,
        10,
        80,
    )[0]
    if merchant_score_without_penalty <= merchant_score_with_penalty:
        raise AssertionError("关闭商家模板降权后评分没有恢复")

    status_test_file = "item_statuses_self_test.json"
    status_archive_file = f"{status_test_file}.archive.json"
    try:
        save_item_statuses(
            {
                "https://www.goofish.com/item?id=status-test": {
                    "status": "收藏",
                    "updated_at": "2026-06-07 12:00:00",
                    "keyword": "Mac mini M4",
                    "title": "测试商品",
                    "url": "https://www.goofish.com/item?id=status-test",
                }
            },
            file_path=status_test_file,
        )
        loaded_statuses = load_item_statuses(status_test_file)
        if loaded_statuses["https://www.goofish.com/item?id=status-test"]["status"] != "收藏":
            raise AssertionError("命中状态保存/读取失败")
        save_item_statuses(
            {
                f"status-{index}": {
                    "status": "收藏" if index % 2 else "未处理",
                    "updated_at": f"2026-06-07 12:00:{index:02d}",
                    "keyword": "归档测试",
                    "title": f"状态归档 {index}",
                    "url": f"https://example.com/status-{index}",
                }
                for index in range(5)
            },
            file_path=status_test_file,
            limit=2,
        )
        if not os.path.exists(status_archive_file):
            raise AssertionError("状态归档文件未生成")
    finally:
        for path in (status_test_file, status_archive_file):
            if os.path.exists(path):
                os.remove(path)

    history_test_file = "hit_history_archive_self_test.json"
    history_archive_file = f"{history_test_file}.archive.json"
    try:
        save_hit_history(
            [
                {
                    "time": f"2026-06-07 12:00:{index:02d}",
                    "status": "未处理",
                    "platform_name": "闲鱼",
                    "keyword": "归档测试",
                    "page_number": 1,
                    "price": index,
                    "score": index,
                    "level": "测试",
                    "quality_reason": "归档测试",
                    "title": f"历史归档 {index}",
                    "url": f"https://example.com/history-{index}",
                }
                for index in range(6)
            ],
            file_path=history_test_file,
            limit=3,
        )
        if len(load_hit_history(history_test_file)) != 3 or not os.path.exists(history_archive_file):
            raise AssertionError("历史命中归档失败")
    finally:
        for path in (history_test_file, history_archive_file):
            if os.path.exists(path):
                os.remove(path)

    hit_store_test_file = "scanned_items_self_test.json"
    try:
        hit_store = HitStore(hit_store_test_file)
        hit_store.reset(["legacy-id", "hit:kept", "hit:kept"])
        if hit_store.has_seen_hit("legacy-id") or not hit_store.has_seen_hit("kept"):
            raise AssertionError("HitStore 新旧去重记录识别失败")
        if hit_store.save():
            raise AssertionError("HitStore 未变更时不应写盘")
        if not hit_store.remember_hit("new-id"):
            raise AssertionError("HitStore 新命中写入失败")
        if not hit_store.save():
            raise AssertionError("HitStore 有变更时未写盘")
        reloaded_hit_store = HitStore(hit_store_test_file)
        reloaded_hit_store.load()
        if not reloaded_hit_store.has_seen_hit("new-id"):
            raise AssertionError("HitStore 保存后读取失败")
    finally:
        if os.path.exists(hit_store_test_file):
            os.remove(hit_store_test_file)

    keyword_alias_cases = [
        ("苹果手机", "个人自用 iPhone 15 Pro 256G，电池健康 92，功能正常"),
        ("苹果电脑", "便宜出99新 MacBook Pro 13寸，办公学习剪辑都正常"),
    ]
    for keyword, title in keyword_alias_cases:
        if not worker.title_matches_keyword(title, keyword):
            raise AssertionError(f"关键词同义词匹配失败：{keyword} | {title}")

    print("[DEBUG] self-test: filter rules OK")


