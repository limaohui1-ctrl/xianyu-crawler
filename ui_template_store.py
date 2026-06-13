"""Template store, market, CRUD, and field-editor helpers."""

from ui_registry import register

import json
from copy import deepcopy

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QCheckBox, QComboBox, QLabel, QListWidget, QListWidgetItem, QMessageBox, QTableWidgetItem
from universal_core import AI_MODEL_USE_CASE_PRESETS, FieldRule, SiteTemplate, search_template_market, template_market_items

@register("reload_templates")
def reload_templates(self):
    self.templates = self.template_store.load()
    self.template_combo.clear()
    self.template_list.clear()
    for template in self.templates:
        self.template_combo.addItem(template.name)
        item = QListWidgetItem(template.name)
        item.setToolTip(template.notes)
        self.template_list.addItem(item)
    if self.templates:
        self.template_list.setCurrentRow(0)
    if hasattr(self, "template_market_table"):
        self.refresh_template_market()

@register("refresh_template_market")
def refresh_template_market(self):
    if not hasattr(self, "template_market_table"):
        return
    query = self.template_market_search_input.text().strip() if hasattr(self, "template_market_search_input") else ""
    if self.template_market_category_combo.count() == 0:
        categories = sorted({item.get("category", "") for item in search_template_market() if item.get("category")})
        self.template_market_category_combo.blockSignals(True)
        self.template_market_category_combo.addItem("全部分类")
        for category in categories:
            self.template_market_category_combo.addItem(category)
        self.template_market_category_combo.blockSignals(False)
    category = self.template_market_category_combo.currentText() or "全部分类"
    items = search_template_market(query, category)
    self.template_market_items = items
    self.template_market_table.setRowCount(0)
    use_cases = AI_MODEL_USE_CASE_PRESETS
    for item in items:
        template = item.get("template") or SiteTemplate(item.get("name", ""))
        row = self.template_market_table.rowCount()
        self.template_market_table.insertRow(row)
        use_case = use_cases.get(item.get("recommended_use_case") or "web_scrape", {})
        values = [
            item.get("category", ""),
            template.name,
            len(template.field_rules),
            use_case.get("name", item.get("recommended_use_case", "")),
            template.notes,
        ]
        for column, value in enumerate(values):
            cell = QTableWidgetItem(str(value))
            cell.setToolTip(str(value))
            cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.template_market_table.setItem(row, column, cell)
    if items:
        self.template_market_table.selectRow(0)

@register("selected_market_template_item")
def selected_market_template_item(self):
    row = self.template_market_table.currentRow() if hasattr(self, "template_market_table") else -1
    if row < 0 or row >= len(getattr(self, "template_market_items", [])):
        return None
    return self.template_market_items[row]

@register("install_market_template")
def install_market_template(self, apply_to_task=False):
    item = self.selected_market_template_item()
    if not item:
        QMessageBox.information(self, "提示", "请先在模板市场里选择一个模板。")
        return False
    template = deepcopy(item.get("template") or SiteTemplate(item.get("name", "未命名模板")))
    self.upsert_template(template)
    use_case_key = item.get("recommended_use_case") or ""
    use_case_name = AI_MODEL_USE_CASE_PRESETS.get(use_case_key, {}).get("name", use_case_key)
    self.append_log(f"已从模板市场安装：{template.name}（推荐模型用途：{use_case_name}）")
    if apply_to_task:
        self.show_main_tab("批量采集")
        self.append_log(f"当前采集任务已使用模板：{template.name}")
    return True

@register("select_template_by_name")
def select_template_by_name(self, template_name):
    index = self.template_combo.findText(template_name)
    if index >= 0:
        self.template_combo.setCurrentIndex(index)
    list_items = self.template_list.findItems(template_name, Qt.MatchFlag.MatchExactly)
    if list_items:
        self.template_list.setCurrentItem(list_items[0])
    return index >= 0

@register("upsert_template")
def upsert_template(self, template):
    templates = list(getattr(self, "templates", []) or self.template_store.load())
    existing_index = next((index for index, saved in enumerate(templates) if saved.name == template.name), -1)
    if existing_index >= 0:
        templates[existing_index] = template
        target_index = existing_index
    else:
        templates.append(template)
        target_index = len(templates) - 1
    self.template_store.save(templates)
    self.reload_templates()
    self.template_list.setCurrentRow(max(0, target_index))
    self.select_template_by_name(template.name)
    return target_index

@register("load_template_to_editor")
def load_template_to_editor(self, row):
    if row < 0 or row >= len(self.templates):
        return
    template = self.templates[row]
    self.template_name_input.setText(template.name)
    self.template_domain_input.setText(template.domain)
    index = self.template_type_combo.findData(template.template_type)
    self.template_type_combo.setCurrentIndex(max(0, index))
    self.next_page_selector_input.setText(template.next_page_selector)
    self.template_notes_input.setPlainText(template.notes)
    self.field_table.setRowCount(0)
    for rule in template.field_rules:
        self.add_field_row(rule)

@register("add_field_row")
def add_field_row(self, rule=None):
    rule = rule or FieldRule("标题", "h1")
    row = self.field_table.rowCount()
    self.field_table.insertRow(row)
    self.field_table.setItem(row, 0, QTableWidgetItem(rule.name))
    self.field_table.setItem(row, 1, QTableWidgetItem(rule.selector))
    attr_combo = QComboBox()
    for attr in ("text", "href", "src", "content", "data-src"):
        attr_combo.addItem(attr)
    attr_index = attr_combo.findText(rule.attr)
    attr_combo.setCurrentIndex(max(0, attr_index))
    self.field_table.setCellWidget(row, 2, attr_combo)
    multi_check = QCheckBox()
    multi_check.setChecked(rule.multiple)
    self.field_table.setCellWidget(row, 3, multi_check)

@register("remove_selected_field")
def remove_selected_field(self):
    rows = sorted({index.row() for index in self.field_table.selectedIndexes()}, reverse=True)
    for row in rows:
        self.field_table.removeRow(row)
