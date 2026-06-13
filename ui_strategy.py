"""Strategy comparison and dual-run helpers for simple collection."""

from ui_registry import register


@register("record_strategy_label")
def record_strategy_label(self, record):
    label = record.get("simple_collect_depth") or record.get("crawl_strategy") or record.get("strategy") or ""
    if label:
        return str(label)
    run_id = int(record.get("run_id") or 0)
    if run_id:
        config = self.database.run_config(run_id)
        label = (config or {}).get("simple_collect_depth") or ""
        if label:
            return str(label)
    return ""

@register("strategy_comparison_rows")
def strategy_comparison_rows(self, records=None):
    grouped = {}
    for record in list(records if records is not None else getattr(self, "records", [])):
        if not isinstance(record, dict):
            continue
        label = self.record_strategy_label(record)
        if not label:
            continue
        self.ensure_record_completeness(record)
        bucket = grouped.setdefault(
            label,
            {
                "strategy": label,
                "count": 0,
                "scores": [],
                "images": 0,
                "links": 0,
                "tables": 0,
                "errors": 0,
                "urls": set(),
            },
        )
        bucket["count"] += 1
        bucket["scores"].append(int(record.get("completeness_score") or 0))
        bucket["images"] += len(record.get("images", []) or [])
        bucket["links"] += len(record.get("links", []) or [])
        bucket["tables"] += len(record.get("tables", []) or [])
        bucket["errors"] += 1 if record.get("error") else 0
        if record.get("url"):
            bucket["urls"].add(record.get("url"))
    rows = []
    for bucket in grouped.values():
        count = max(1, int(bucket.get("count") or 0))
        avg_score = round(sum(bucket.get("scores") or []) / count)
        rows.append(
            {
                "strategy": bucket.get("strategy", ""),
                "count": bucket.get("count", 0),
                "avg_score": avg_score,
                "images": bucket.get("images", 0),
                "links": bucket.get("links", 0),
                "tables": bucket.get("tables", 0),
                "errors": bucket.get("errors", 0),
                "url_count": len(bucket.get("urls", set())),
                "value_score": avg_score
                + min(15, int(bucket.get("images", 0)))
                + min(15, int(bucket.get("links", 0)) // 2)
                + min(15, int(bucket.get("tables", 0)) * 2)
                - int(bucket.get("errors", 0)) * 10,
            }
        )
    rows.sort(key=lambda row: (-int(row.get("value_score", 0)), row.get("strategy", "")))
    return rows

@register("build_strategy_comparison_report")
def build_strategy_comparison_report(self, records=None):
    rows = self.strategy_comparison_rows(records)
    if len(rows) < 2:
        return {
            "summary": "实测对比：需要至少两种策略样本，例如先普通抓一次，再完整抓一次",
            "best": "",
            "delta": 0,
            "rows": rows,
        }
    best = rows[0]
    baseline = next((row for row in rows if row.get("strategy") == "普通"), rows[-1])
    delta = int(best.get("avg_score") or 0) - int(baseline.get("avg_score") or 0)
    more_links = int(best.get("links") or 0) - int(baseline.get("links") or 0)
    more_images = int(best.get("images") or 0) - int(baseline.get("images") or 0)
    more_tables = int(best.get("tables") or 0) - int(baseline.get("tables") or 0)
    summary = (
        f"实测对比：推荐 {best.get('strategy')}；完整度 {delta:+d} 分，"
        f"链接 {more_links:+d}，图片 {more_images:+d}，表格 {more_tables:+d}"
    )
    return {
        "summary": summary,
        "best": best.get("strategy", ""),
        "delta": delta,
        "rows": rows,
    }

@register("strategy_dual_run_overrides")
def strategy_dual_run_overrides(self, mode):
    depth_config = self.simple_collect_depth_config(mode)
    return {
        "scrape_subpages": True,
        "subpage_limit": depth_config["subpage_limit"],
        "selected_subpage_urls": [],
        "simple_auto_subpages": True,
        "simple_collect_depth": depth_config["label"],
        "skip_unchanged": False,
    }

@register("prepare_strategy_dual_run_mode")
def prepare_strategy_dual_run_mode(self, mode):
    depth_config = self.apply_simple_depth_mode(mode)
    self.use_browser_checkbox.setChecked(True)
    self.page_limit_input.setValue(depth_config["page_limit"])
    self.scroll_times_input.setValue(max(depth_config["scroll_times"], self.scroll_times_input.value()))
    self.delay_input.setValue(max(1, self.delay_input.value()))
    self.keep_login_checkbox.setChecked(False)
    self.subpage_checkbox.setChecked(False)
    self.subpage_limit_input.setValue(0)
    self.selected_subpage_urls = []
    return depth_config

@register("start_strategy_dual_run")
def start_strategy_dual_run(self):
    if self.worker:
        if hasattr(self, "simple_strategy_compare_label"):
            self.simple_strategy_compare_label.setText("实测对比：当前采集运行中，完成后再开始对比")
        return False
    self.sync_simple_inputs_to_background()
    urls = self.urls_from_input()
    if not urls:
        self.simple_information("提示", "请先输入至少一个网址，再运行实测对比。")
        self.set_simple_flow_step("输入")
        return False
    self.simple_ai_field_rules = []
    self.simple_ai_suggest_pending = False
    self.clear_current_results()
    self.simple_merge_subpage_results = True
    self.simple_subpage_parent_map = {}
    self.url_input.setPlainText("\n".join(urls))
    if hasattr(self, "ai_url_input"):
        self.ai_url_input.setText(urls[0])
    self.simple_select_default_template()
    depth_config = self.prepare_strategy_dual_run_mode("normal")
    self.strategy_dual_run_active = True
    self.strategy_dual_run_ready_report = False
    self.strategy_dual_run_step = "普通"
    self.strategy_dual_run_urls = list(urls)
    self.strategy_dual_run_records_before = len(self.records)
    if hasattr(self, "simple_strategy_compare_label"):
        self.simple_strategy_compare_label.setText("实测对比：正在采集普通模式样本")
    if hasattr(self, "simple_status_label"):
        self.simple_status_label.setText("实测对比：先用普通模式采集样本")
    if hasattr(self, "simple_progress_label"):
        self.simple_progress_label.setText(depth_config["progress"])
    self.set_simple_flow_step("采集")
    self.append_log("实测对比已启动：先运行普通模式，再自动运行完整模式。")
    self.start_collecting(
        skip_confirmation=True,
        runtime_overrides=self.strategy_dual_run_overrides("normal"),
    )
    return True

@register("maybe_continue_strategy_dual_run")
def maybe_continue_strategy_dual_run(self, status):
    if not getattr(self, "strategy_dual_run_active", False):
        return False
    if status not in ("finished", "partial"):
        self.strategy_dual_run_active = False
        self.strategy_dual_run_step = ""
        self.strategy_dual_run_urls = []
        if hasattr(self, "simple_strategy_compare_label"):
            self.simple_strategy_compare_label.setText(f"实测对比：采集结束为 {status}，未继续自动对比")
        return False
    if self.strategy_dual_run_step == "普通":
        self.strategy_dual_run_step = "完整"
        urls = list(self.strategy_dual_run_urls or self.urls_from_input())
        if urls:
            self.url_input.setPlainText("\n".join(urls))
        depth_config = self.prepare_strategy_dual_run_mode("complete")
        if hasattr(self, "simple_strategy_compare_label"):
            self.simple_strategy_compare_label.setText("实测对比：普通样本完成，正在采集完整模式样本")
        if hasattr(self, "simple_status_label"):
            self.simple_status_label.setText("实测对比：继续用完整模式采集样本")
        if hasattr(self, "simple_progress_label"):
            self.simple_progress_label.setText(depth_config["progress"])
        self.append_log("实测对比：普通模式完成，开始完整模式。")
        self.start_collecting(
            skip_confirmation=True,
            runtime_overrides=self.strategy_dual_run_overrides("complete"),
        )
        return True
    if self.strategy_dual_run_step == "完整":
        self.strategy_dual_run_active = False
        self.strategy_dual_run_step = ""
        self.strategy_dual_run_urls = []
        self.strategy_dual_run_ready_report = True
    return False

@register("finalize_strategy_dual_run_report")
def finalize_strategy_dual_run_report(self):
    if not getattr(self, "strategy_dual_run_ready_report", False):
        return False
    self.strategy_dual_run_ready_report = False
    records = getattr(self, "records", [])[int(self.strategy_dual_run_records_before or 0):]
    report = self.build_strategy_comparison_report(records)
    if len(report.get("rows", [])) < 2:
        report = self.build_strategy_comparison_report()
    self.latest_strategy_comparison_report = report
    summary = report.get("summary", "实测对比：等待两种策略样本")
    if hasattr(self, "simple_strategy_compare_label"):
        self.simple_strategy_compare_label.setText(summary)
    if hasattr(self, "simple_status_label"):
        self.simple_status_label.setText(summary)
    if hasattr(self, "simple_progress_label"):
        rows_text = "；".join(
            f"{row.get('strategy')} 完整度{row.get('avg_score')} 链接{row.get('links')}"
            for row in report.get("rows", [])[:3]
        )
        self.simple_progress_label.setText(f"{summary}。{rows_text}")
    best = report.get("best", "")
    if best == "完整":
        self.apply_complete_crawl_settings()
    elif best == "深度":
        self.apply_simple_depth_mode("deep")
    elif best == "普通":
        self.apply_simple_depth_mode("normal")
    return bool(report.get("rows"))

@register("simple_run_strategy_comparison")
def simple_run_strategy_comparison(self):
    report = self.build_strategy_comparison_report()
    if len(report.get("rows", [])) < 2:
        return self.start_strategy_dual_run()
    self.latest_strategy_comparison_report = report
    summary = report.get("summary", "实测对比：等待两种策略样本")
    if hasattr(self, "simple_strategy_compare_label"):
        self.simple_strategy_compare_label.setText(summary)
    best = report.get("best", "")
    if best == "完整":
        self.apply_complete_crawl_settings()
    elif best == "深度":
        deep_index = self.simple_depth_combo.findData("deep") if hasattr(self, "simple_depth_combo") else -1
        if deep_index >= 0:
            self.simple_depth_combo.setCurrentIndex(deep_index)
    elif best == "普通":
        normal_index = self.simple_depth_combo.findData("normal") if hasattr(self, "simple_depth_combo") else -1
        if normal_index >= 0:
            self.simple_depth_combo.setCurrentIndex(normal_index)
    if hasattr(self, "simple_progress_label"):
        rows_text = "；".join(
            f"{row.get('strategy')} 完整度{row.get('avg_score')} 链接{row.get('links')}"
            for row in report.get("rows", [])[:3]
        )
        self.simple_progress_label.setText(f"{summary}。{rows_text}")
    return bool(report.get("rows"))
