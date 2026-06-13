"""Template CRUD, editor, and field operations."""

from ui_registry import register

from PyQt6.QtWidgets import QCheckBox, QComboBox, QMessageBox, QTableWidgetItem

import json


from universal_core import (
    FieldRule,
    SiteTemplate,
    build_selector_from_clicked_element,
    normalize_url,
    scene_template_presets,
)
from core_urls import (
    normalize_url,
)



@register("new_template")
def new_template(self):
    template = SiteTemplate(
        name=f"新模板{len(self.templates) + 1}",
        domain="",
        template_type="auto",
    )
    self.templates.append(template)
    self.template_store.save(self.templates)
    self.reload_templates()
    self.template_list.setCurrentRow(len(self.templates) - 1)

@register("apply_scene_preset")
def apply_scene_preset(self):
    preset_name = self.scene_preset_combo.currentText()
    preset = scene_template_presets().get(preset_name)
    if not preset:
        QMessageBox.information(self, "提示", "请选择一个场景模板。")
        return
    self.template_name_input.setText(preset.name)
    self.template_domain_input.setText(preset.domain)
    index = self.template_type_combo.findData(preset.template_type)
    self.template_type_combo.setCurrentIndex(max(0, index))
    self.next_page_selector_input.setText(preset.next_page_selector)
    self.template_notes_input.setPlainText(preset.notes)
    self.field_table.setRowCount(0)
    for rule in preset.field_rules:
        self.add_field_row(rule)
    self.append_log(f"已套用场景模板：{preset.name}，可直接保存或开始采集。")

@register("collect_field_rules_from_table")
def collect_field_rules_from_table(self):
    rules = []
    for row in range(self.field_table.rowCount()):
        name_item = self.field_table.item(row, 0)
        selector_item = self.field_table.item(row, 1)
        attr_widget = self.field_table.cellWidget(row, 2)
        multi_widget = self.field_table.cellWidget(row, 3)
        name = name_item.text().strip() if name_item else ""
        selector = selector_item.text().strip() if selector_item else ""
        if not name or not selector:
            continue
        attr = attr_widget.currentText() if isinstance(attr_widget, QComboBox) else "text"
        multiple = multi_widget.isChecked() if isinstance(multi_widget, QCheckBox) else False
        rules.append(FieldRule(name, selector, attr, multiple))
    return rules

@register("save_current_template")
def save_current_template(self):
    row = self.template_list.currentRow()
    if row < 0:
        return
    template = SiteTemplate(
        name=self.template_name_input.text().strip() or "未命名模板",
        domain=self.template_domain_input.text().strip().lower(),
        template_type=self.template_type_combo.currentData() or "auto",
        field_rules=self.collect_field_rules_from_table(),
        next_page_selector=self.next_page_selector_input.text().strip(),
        notes=self.template_notes_input.toPlainText().strip(),
    )
    self.templates[row] = template
    self.template_store.save(self.templates)
    self.reload_templates()
    self.template_list.setCurrentRow(row)
    self.select_template_by_name(template.name)
    self.append_log(f"已保存模板：{template.name}")

@register("delete_current_template")
def delete_current_template(self):
    row = self.template_list.currentRow()
    if row < 0:
        return
    if len(self.templates) <= 1:
        QMessageBox.information(self, "提示", "至少保留一个模板。")
        return
    del self.templates[row]
    self.template_store.save(self.templates)
    self.reload_templates()

@register("generate_selector_from_helper")
def generate_selector_from_helper(self):
    selector = build_selector_from_clicked_element(
        self.click_tag_input.text(),
        self.click_id_input.text(),
        self.click_class_input.text().split(),
    )
    selected_rows = {index.row() for index in self.field_table.selectedIndexes()}
    if selected_rows:
        row = min(selected_rows)
    else:
        self.add_field_row(FieldRule("自定义字段", selector))
        row = self.field_table.rowCount() - 1
    self.field_table.setItem(row, 1, QTableWidgetItem(selector))
    self.append_log(f"已生成选择器：{selector}")

@register("visual_pick_field")
def visual_pick_field(self):
    url = normalize_url(self.pick_url_input.text())
    if not url:
        urls = self.urls_from_input()
        url = urls[0] if urls else ""
    if not url:
        QMessageBox.information(self, "提示", "请先输入点选网址或采集任务网址。")
        return
    field_name = self.pick_field_name_input.text().strip() or "自定义字段"
    self.append_log(f"正在打开点选浏览器：{url}")
    try:
        result = pick_element_from_page(url)
    except Exception as exc:
        QMessageBox.warning(self, "点选失败", str(exc))
        return
    if not result:
        self.append_log("点选已取消或未获得结果。")
        return
    self.click_tag_input.setText(result.get("tag", ""))
    self.click_id_input.setText(result.get("id", ""))
    self.click_class_input.setText(" ".join(result.get("classes", [])))
    selector = result.get("selector") or build_selector_from_clicked_element(
        result.get("tag", ""),
        result.get("id", ""),
        result.get("classes", []),
    )
    attr = "text"
    if result.get("tag") == "img":
        attr = "src"
    elif result.get("tag") == "a":
        attr = "href"
    self.add_field_row(FieldRule(field_name, selector, attr, False))
    self.append_log(
        f"已添加点选字段：{field_name} -> {selector} | "
        f"{result.get('text', '')[:80]}"
    )
