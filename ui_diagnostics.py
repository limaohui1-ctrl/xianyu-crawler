"""Crawl diagnosis, repair-plan, and sample-verification helpers."""

from ui_registry import register
from universal_core import compact_text, normalize_url
from core_urls import normalize_url

@register("record_links_matching_tokens")
def record_links_matching_tokens(self, record, tokens):
    matched = []
    for link in record.get("links", []) or []:
        if isinstance(link, dict):
            text = str(link.get("text") or link.get("title") or "")
            url = str(link.get("url") or link.get("href") or "")
        else:
            text = str(link)
            url = str(link)
        combined = f"{text} {url}".lower()
        if any(token in combined for token in tokens):
            matched.append({"text": text, "url": url})
    return matched

@register("pagination_like_links")
def pagination_like_links(self, record):
    tokens = (
        "下一页",
        "下页",
        "翻页",
        "页码",
        "加载更多",
        "pagination",
        "pager",
        "next",
        "page=",
        "/page",
        "page/",
    )
    return self.record_links_matching_tokens(record, tokens)

@register("detail_like_links")
def detail_like_links(self, record):
    tokens = (
        "详情",
        "商品",
        "宝贝",
        "查看",
        "detail",
        "item",
        "product",
        "goods",
        "offer",
        "/p/",
        "/item/",
        "/detail",
        "/product",
    )
    return self.record_links_matching_tokens(record, tokens)

@register("crawl_diagnosis_for_record")
def crawl_diagnosis_for_record(self, record):
    self.ensure_record_completeness(record)
    missing = set(record.get("completeness_missing", []) or [])
    score = int(record.get("completeness_score") or 0)
    body_text = compact_text(record.get("body", ""), 2000)
    error_text = compact_text(record.get("error", ""), 500)
    link_count = len(record.get("links", []) or [])
    image_count = len(record.get("images", []) or [])
    table_count = len(record.get("tables", []) or [])
    pagination_links = self.pagination_like_links(record)
    detail_links = self.detail_like_links(record)
    if error_text:
        lower_error = error_text.lower()
        if any(token in lower_error for token in ("403", "401", "captcha", "验证码", "登录", "forbidden", "access denied")):
            return {
                "reason": "反爬或权限限制",
                "advice": "改用真实浏览器、保持登录，并加大延迟后重试。",
                "severity": "需处理",
            }
        return {
            "reason": "请求失败",
            "advice": "查看错误列，降低速度或稍后重试。",
            "severity": "需处理",
        }
    if score >= 85:
        return {"reason": "资料较完整", "advice": "可以直接导出或加入监控。", "severity": "正常"}
    if pagination_links and ("正文" in missing or score < 70):
        return {
            "reason": "分页可能未继续",
            "advice": "应用诊断建议会切到完整模式，提高翻页、滚动和等待，继续读取下一页/更多内容。",
            "severity": "需处理",
            "pagination_links": len(pagination_links),
            "detail_links": len(detail_links),
        }
    if detail_links and missing.intersection({"图片", "价格", "表格/规格", "正文"}):
        return {
            "reason": "子链接未展开",
            "advice": "使用“重抓低完整度”让完整模式自动进入同站详情/商品子链接，补图片、价格和规格。",
            "severity": "需处理",
            "pagination_links": len(pagination_links),
            "detail_links": len(detail_links),
        }
    if len(body_text) < 40 and image_count == 0 and table_count == 0:
        return {
            "reason": "疑似动态加载",
            "advice": "使用完整模式重抓，增加滚动次数和等待时间。",
            "severity": "需处理",
        }
    if missing.intersection({"图片", "价格", "表格/规格"}) and link_count:
        return {
            "reason": "详情页可能未展开",
            "advice": "使用“重抓低完整度”让完整模式补详情页、图片和规格。",
            "severity": "需处理",
        }
    if body_text and len(missing) >= 3:
        return {
            "reason": "字段规则可能不匹配",
            "advice": "点击 AI 建议列或到 AI 抓取工作台修复字段规则。",
            "severity": "需确认",
        }
    if "链接" in missing and missing.intersection({"图片", "价格", "表格/规格"}):
        return {
            "reason": "子链接候选不足",
            "advice": "应用诊断建议会切到完整模式；若仍抓不到，请到 AI 工作台扫描并手动选择子页面链接。",
            "severity": "需确认",
            "pagination_links": len(pagination_links),
            "detail_links": len(detail_links),
        }
    return {
        "reason": "页面资料偏少",
        "advice": "抽查原网页；若网页本身信息少，可接受低完整度或减少字段要求。",
        "severity": "需确认",
    }

@register("simple_crawl_diagnosis_rows")
def simple_crawl_diagnosis_rows(self, records=None):
    rows = []
    for record in list(records if records is not None else getattr(self, "records", [])):
        if not isinstance(record, dict):
            continue
        diagnosis = self.crawl_diagnosis_for_record(record)
        rows.append(
            {
                "url": normalize_url(record.get("url", "")),
                "title": record.get("title") or "(无标题)",
                "score": int(record.get("completeness_score") or 0),
                "missing": "、".join(record.get("completeness_missing", []) or []),
                **diagnosis,
            }
        )
    return rows

@register("simple_crawl_diagnosis_text")
def simple_crawl_diagnosis_text(self):
    rows = self.simple_crawl_diagnosis_rows()
    if not rows:
        return "诊断建议：等待结果"
    weak_rows = [row for row in rows if int(row.get("score") or 0) < 60 or row.get("severity") != "正常"]
    if not weak_rows:
        return f"诊断建议：{len(rows)} 条资料较完整，可以导出或加入监控"
    reason_counts = {}
    reason_severity = {}
    severity_rank = {"需处理": 2, "需确认": 1, "正常": 0}
    for row in weak_rows:
        reason = row.get("reason", "页面资料偏少")
        reason_counts[reason] = reason_counts.get(reason, 0) + 1
        reason_severity[reason] = max(
            reason_severity.get(reason, 0),
            severity_rank.get(row.get("severity", "需确认"), 1),
        )
    top_reason, top_count = sorted(
        reason_counts.items(),
        key=lambda item: (reason_severity.get(item[0], 0), item[1]),
        reverse=True,
    )[0]
    top_row = next((row for row in weak_rows if row.get("reason") == top_reason), weak_rows[0])
    return f"诊断建议：{len(weak_rows)} 条需处理；主要是{top_reason} {top_count} 条。建议：{top_row.get('advice', '')}"

@register("simple_repair_plan_groups")
def simple_repair_plan_groups(self, records=None):
    categories = {
        "pagination": {
            "label": "分页",
            "button": "重抓分页",
            "reasons": {"分页可能未继续"},
            "urls": [],
        },
        "subpages": {
            "label": "子链接",
            "button": "重抓子链接",
            "reasons": {"子链接未展开", "详情页可能未展开", "子链接候选不足", "疑似动态加载"},
            "urls": [],
        },
        "login": {
            "label": "登录/请求",
            "button": "登录重试",
            "reasons": {"反爬或权限限制", "请求失败"},
            "urls": [],
        },
        "fields": {
            "label": "字段",
            "button": "AI 修字段",
            "reasons": {"字段规则可能不匹配"},
            "urls": [],
        },
    }
    for row in self.simple_crawl_diagnosis_rows(records):
        if row.get("severity") == "正常":
            continue
        url = normalize_url(row.get("url", ""))
        reason = row.get("reason", "")
        if not url:
            continue
        for group in categories.values():
            if reason in group["reasons"] and url not in group["urls"]:
                group["urls"].append(url)
    return categories

@register("simple_repair_plan_text")
def simple_repair_plan_text(self):
    groups = self.simple_repair_plan_groups()
    active = [group for group in groups.values() if group.get("urls")]
    if not active:
        return "修复方案：等待诊断，或当前结果不需要自动修复"
    parts = [f"{group['label']} {len(group['urls'])} 条 -> {group['button']}" for group in active]
    return "修复方案：" + "；".join(parts)

@register("start_complete_retry_for_urls")
def start_complete_retry_for_urls(self, urls, status_text, progress_text):
    urls = [normalize_url(url) for url in urls or []]
    urls = [url for index, url in enumerate(urls) if url and url not in urls[:index]]
    if not urls:
        self.simple_information("提示", "当前没有可重抓的网址。")
        return False
    if self.worker:
        self.simple_status_label.setText("正在采集，请先等待当前任务结束")
        self.simple_information("提示", "正在采集，请先等待当前任务结束。")
        return False
    depth_config = self.apply_complete_crawl_settings()
    self.simple_select_default_template()
    self.start_retry_comparison_tracking(urls, reason=status_text)
    self.simple_merge_subpage_results = True
    self.simple_subpage_parent_map = {}
    self.simple_url_input.setPlainText("\n".join(urls))
    self.sync_simple_inputs_to_background()
    self.simple_status_label.setText(status_text)
    self.simple_progress_label.setText(progress_text)
    self.append_log(f"{status_text}：{len(urls)} 个网址。")
    self.start_collecting(
        skip_confirmation=True,
        runtime_overrides={
            "scrape_subpages": True,
            "subpage_limit": depth_config["subpage_limit"],
            "selected_subpage_urls": [],
            "simple_auto_subpages": True,
            "simple_collect_depth": depth_config["label"],
            "skip_unchanged": False,
        },
    )
    return True

@register("simple_apply_repair_plan_action")
def simple_apply_repair_plan_action(self, category):
    groups = self.simple_repair_plan_groups()
    group = groups.get(category, {})
    urls = group.get("urls", [])
    if not urls:
        self.simple_status_label.setText(f"修复方案：当前没有需要{group.get('button', '处理')}的网址")
        return False
    if category == "fields":
        if self.maybe_start_simple_ai_suggest_fields(urls):
            self.simple_status_label.setText(f"修复方案：AI 正在为 {len(urls)} 条结果整理字段")
        else:
            self.simple_status_label.setText("修复方案：请检查 AI 设置后再修字段")
        return True
    if category == "login":
        self.apply_blocked_crawl_settings()
        self.simple_url_input.setPlainText("\n".join(urls))
        self.sync_simple_inputs_to_background()
        self.simple_status_label.setText(f"修复方案：已启用真实浏览器和保留登录，准备重试 {len(urls)} 条")
        self.simple_progress_label.setText("下一次采集会保留登录状态，并用更慢速度访问")
        return True
    if category == "pagination":
        return self.start_complete_retry_for_urls(
            urls,
            f"正在完整模式重抓 {len(urls)} 条分页不足结果",
            "后台：提高翻页、滚动和等待，继续读取下一页/更多内容",
        )
    if category == "subpages":
        return self.start_complete_retry_for_urls(
            urls,
            f"正在完整模式重抓 {len(urls)} 条子链接不足结果",
            "后台：自动进入同站详情/商品子链接，补图片、价格、规格和正文",
        )
    return False

@register("primary_simple_crawl_diagnosis")
def primary_simple_crawl_diagnosis(self):
    rows = self.simple_crawl_diagnosis_rows()
    weak_rows = [row for row in rows if int(row.get("score") or 0) < 60 or row.get("severity") != "正常"]
    if not weak_rows:
        return {}
    severity_rank = {"需处理": 2, "需确认": 1, "正常": 0}
    weak_rows.sort(
        key=lambda row: (
            severity_rank.get(row.get("severity", "需确认"), 1),
            100 - int(row.get("score") or 0),
        ),
        reverse=True,
    )
    return weak_rows[0]

@register("apply_complete_crawl_settings")
def apply_complete_crawl_settings(self):
    complete_index = self.simple_depth_combo.findData("complete") if hasattr(self, "simple_depth_combo") else -1
    if complete_index >= 0:
        self.simple_depth_combo.setCurrentIndex(complete_index)
    depth_config = self.simple_collect_depth_config()
    self.use_browser_checkbox.setChecked(True)
    self.page_limit_input.setValue(max(self.page_limit_input.value(), depth_config["page_limit"]))
    self.scroll_times_input.setValue(max(self.scroll_times_input.value(), depth_config["scroll_times"]))
    self.delay_input.setValue(max(self.delay_input.value(), 2))
    return depth_config

@register("apply_blocked_crawl_settings")
def apply_blocked_crawl_settings(self):
    self.use_browser_checkbox.setChecked(True)
    self.keep_login_checkbox.setChecked(True)
    self.delay_input.setValue(max(self.delay_input.value(), 3))
    self.scroll_times_input.setValue(max(self.scroll_times_input.value(), 2))

@register("simple_apply_diagnosis_action")
def simple_apply_diagnosis_action(self):
    diagnosis = self.primary_simple_crawl_diagnosis()
    if not diagnosis:
        self.simple_information("提示", "当前没有需要处理的诊断建议。")
        return False
    reason = diagnosis.get("reason", "")
    if reason in {"疑似动态加载", "详情页可能未展开", "分页可能未继续", "子链接未展开", "子链接候选不足"}:
        self.apply_complete_crawl_settings()
        if self.low_quality_urls():
            self.simple_status_label.setText("已应用诊断建议：完整模式重抓低完整度结果")
            return self.simple_retry_low_quality_items()
        self.simple_status_label.setText("已应用诊断建议：切换到完整模式并提高滚动/等待")
        self.simple_progress_label.setText("下一次采集会使用真实浏览器、完整深度和更长等待")
        return True
    if reason == "反爬或权限限制":
        self.apply_blocked_crawl_settings()
        self.simple_status_label.setText("已应用诊断建议：真实浏览器、保留登录、降低速度")
        self.simple_progress_label.setText("下一次采集会保留登录状态，并用更慢速度访问")
        return True
    if reason == "请求失败":
        self.use_browser_checkbox.setChecked(True)
        self.delay_input.setValue(max(self.delay_input.value(), 3))
        self.simple_status_label.setText("已应用诊断建议：启用真实浏览器并降低速度")
        self.simple_progress_label.setText("下一次采集会用更稳的访问方式重试")
        return True
    if reason == "字段规则可能不匹配":
        urls = [diagnosis.get("url", "")] if diagnosis.get("url", "") else self.urls_from_input()
        urls = [url for url in urls if url]
        if urls and self.maybe_start_simple_ai_suggest_fields(urls):
            self.simple_status_label.setText("已应用诊断建议：AI 正在整理字段规则")
        else:
            self.simple_status_label.setText("已应用诊断建议：请检查 AI 设置后再生成建议列")
        return True
    self.simple_status_label.setText("诊断建议：页面资料可能本身偏少，建议抽查原网页")
    return True

@register("sample_verification_strategy_scores")
def sample_verification_strategy_scores(self, rows):
    scores = {
        "普通": 55,
        "深度": 70,
        "完整": 75,
        "登录浏览器": 65,
        "AI字段修复": 60,
    }
    for row in rows or []:
        reason = row.get("reason", "")
        score = int(row.get("score") or 0)
        if reason == "资料较完整":
            scores["普通"] += 8
            scores["深度"] += 5
        elif reason == "疑似动态加载":
            scores["完整"] += 20
            scores["登录浏览器"] += 12
            scores["普通"] -= 15
        elif reason in {"详情页可能未展开", "子链接未展开"}:
            scores["深度"] += 12
            scores["完整"] += 18
            scores["普通"] -= 10
        elif reason == "分页可能未继续":
            scores["完整"] += 20
            scores["深度"] += 12
            scores["普通"] -= 12
        elif reason == "子链接候选不足":
            scores["完整"] += 10
            scores["AI字段修复"] += 8
        elif reason == "反爬或权限限制":
            scores["登录浏览器"] += 25
            scores["普通"] -= 20
            scores["深度"] -= 8
        elif reason == "字段规则可能不匹配":
            scores["AI字段修复"] += 22
            scores["完整"] += 4
        elif reason == "请求失败":
            scores["登录浏览器"] += 16
            scores["普通"] -= 12
        elif score < 60:
            scores["完整"] += 8
    return {name: max(0, min(100, value)) for name, value in scores.items()}

@register("build_sample_verification_report")
def build_sample_verification_report(self, records=None):
    rows = self.simple_crawl_diagnosis_rows(records)
    if not rows:
        urls = self.urls_from_input()[:5]
        if not urls:
            return {
                "summary": "抽样验证：请先输入或采集 3-5 个网址",
                "recommendation": "",
                "scores": {},
                "rows": [],
            }
        rows = [
            {
                "url": url,
                "title": "(待采样)",
                "score": 0,
                "missing": "",
                "reason": "等待样本",
                "advice": "先用深度模式采集样本，再运行抽样验证。",
                "severity": "需确认",
            }
            for url in urls
        ]
    sample_rows = rows[:5]
    scores = self.sample_verification_strategy_scores(sample_rows)
    recommendation = max(scores.items(), key=lambda item: item[1])[0] if scores else ""
    reason_counts = {}
    for row in sample_rows:
        reason = row.get("reason", "页面资料偏少")
        reason_counts[reason] = reason_counts.get(reason, 0) + 1
    reason_text = "、".join(f"{reason} {count}" for reason, count in sorted(reason_counts.items(), key=lambda item: item[1], reverse=True)[:3])
    summary = f"抽样验证：样本 {len(sample_rows)} 条，推荐 {recommendation}；主要原因：{reason_text}"
    return {
        "summary": summary,
        "recommendation": recommendation,
        "scores": scores,
        "rows": sample_rows,
    }

@register("simple_run_sample_verification")
def simple_run_sample_verification(self):
    report = self.build_sample_verification_report()
    self.latest_sample_verification_report = report
    summary = report.get("summary", "抽样验证：等待样本")
    if hasattr(self, "simple_sample_verify_label"):
        self.simple_sample_verify_label.setText(summary)
    recommendation = report.get("recommendation", "")
    if recommendation == "完整":
        self.apply_complete_crawl_settings()
    elif recommendation == "登录浏览器":
        self.apply_blocked_crawl_settings()
    elif recommendation == "深度":
        deep_index = self.simple_depth_combo.findData("deep") if hasattr(self, "simple_depth_combo") else -1
        if deep_index >= 0:
            self.simple_depth_combo.setCurrentIndex(deep_index)
    elif recommendation == "AI字段修复":
        self.simple_status_label.setText("抽样验证建议：优先使用 AI 建议列修复字段")
    if hasattr(self, "simple_progress_label"):
        score_text = "，".join(f"{name}{score}" for name, score in report.get("scores", {}).items())
        self.simple_progress_label.setText(f"{summary}。策略评分：{score_text}")
    return bool(report.get("rows"))
