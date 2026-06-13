"""Two-click collect, wizard scene, and market recommendation helpers."""

from ui_registry import register

from PyQt6.QtWidgets import QMessageBox


@register("prepare_two_click_collect")
def prepare_two_click_collect(self):
    url = self.first_target_url()
    if not url:
        QMessageBox.information(self, "提示", "请先输入要抓取的网址。")
        return False
    self.configure_collect_wizard()
    if not isinstance(self.latest_ai_result, dict):
        QMessageBox.information(self, "提示", "向导还没有生成可用计划。")
        return False
    if not self.apply_current_ai_task_plan():
        return False
    preview_ok = bool(self.latest_preview_rules and self.ai_table.rowCount() > 0)
    auto_link_mode = bool(hasattr(self, "simple_follow_links_checkbox") and self.simple_follow_links_checkbox.isChecked())
    if auto_link_mode:
        try:
            self.scan_subpage_links_for_current_url()
        except Exception as exc:
            self.append_ai_output(f"后台详情链接扫描失败，已跳过：{exc}")
    urls = self.urls_from_input()
    queue = self.estimated_task_queue(urls)
    self.fill_task_queue_table(queue)
    risks = self.run_preflight_check()
    risk_text = self.risk_summary_text(risks)
    self.show_main_tab("批量采集")
    preview_text = "已完成预采评分" if preview_ok else "预采评分稍后补齐"
    link_text = "、自动判断详情链接正文" if auto_link_mode else ""
    self.collect_progress_label.setText(
        f"2 次点击准备完成：{preview_text}{link_text}、已生成任务队列并完成风险检查。{risk_text}"
    )
    self.append_ai_output(
        f"2 次点击准备完成：模板 {self.selected_template_name()}，网址 {len(urls)} 个，队列 {len(queue)} 项。{preview_text}{link_text}。{risk_text}"
    )
    self.append_log("AI 工作台已准备好采集任务；预采、风险检查和部分高级策略已在后台自动处理。")
    self.refresh_new_user_flow_status("prepared")
    return True

@register("prepare_and_start_collect")
def prepare_and_start_collect(self):
    if self.worker:
        self.append_log("已有采集任务正在运行，未重复启动。")
        return False
    if not self.prepare_two_click_collect():
        return False
    self.append_log("AI 工作台已准备完成，正在开始采集。字段修复、自动保存等会在后台继续处理。")
    self.refresh_new_user_flow_status("running")
    self.start_collecting()
    return True
