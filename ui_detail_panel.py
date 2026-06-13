"""Result detail preview panel construction."""

from ui_registry import register

from PyQt6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QTableWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QHeaderView,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QScrollArea,
    QTableWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,

)


@register("build_detail_panel")
def build_detail_panel(self):
    panel = QWidget()
    layout = QVBoxLayout(panel)

    title_box = QGroupBox("结果详情预览")
    title_layout = QGridLayout(title_box)
    self.detail_title_label = QLabel("未选择结果")
    self.detail_title_label.setWordWrap(True)
    self.detail_url_label = QLabel("")
    self.detail_url_label.setWordWrap(True)
    self.detail_meta_label = QLabel("")
    self.detail_meta_label.setWordWrap(True)
    self.detail_body_output = QTextEdit()
    self.detail_body_output.setReadOnly(True)
    self.detail_body_output.setMaximumHeight(150)
    title_layout.addWidget(QLabel("标题"), 0, 0)
    title_layout.addWidget(self.detail_title_label, 0, 1)
    title_layout.addWidget(QLabel("链接"), 1, 0)
    title_layout.addWidget(self.detail_url_label, 1, 1)
    title_layout.addWidget(QLabel("信息"), 2, 0)
    title_layout.addWidget(self.detail_meta_label, 2, 1)
    title_layout.addWidget(QLabel("正文"), 3, 0)
    title_layout.addWidget(self.detail_body_output, 3, 1)

    image_box = QGroupBox("图片缩略图")
    image_layout = QVBoxLayout(image_box)
    self.image_scroll = QScrollArea()
    self.image_scroll.setWidgetResizable(True)
    self.image_container = QWidget()
    self.image_layout = QHBoxLayout(self.image_container)
    self.image_layout.addStretch(1)
    self.image_scroll.setWidget(self.image_container)
    image_layout.addWidget(self.image_scroll)

    table_box = QGroupBox("链接和表格展开")
    table_layout = QVBoxLayout(table_box)
    self.detail_link_table = QTableWidget(0, 2)
    self.detail_link_table.setHorizontalHeaderLabels(["文字", "链接"])
    self.detail_link_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
    self.detail_link_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
    self.detail_link_table.verticalHeader().setVisible(False)
    self.detail_table_view = QTableWidget(0, 0)
    self.detail_table_view.verticalHeader().setVisible(False)
    table_layout.addWidget(QLabel("页面链接"))
    table_layout.addWidget(self.detail_link_table)
    table_layout.addWidget(QLabel("第一个表格"))
    table_layout.addWidget(self.detail_table_view)

    layout.addWidget(title_box)
    layout.addWidget(image_box)
    layout.addWidget(table_box, 1)
    return panel
