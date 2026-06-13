from .app_core import *

class XianyuMonitorWorker(QObject):
    log_signal = pyqtSignal(str)
    item_found_signal = pyqtSignal(dict)
    comparison_signal = pyqtSignal(dict)
    error_signal = pyqtSignal(str)
    finished_signal = pyqtSignal()

    def __init__(
        self,
        config,
        interval_min,
        interval_max,
        black_words=None,
        smart_match=True,
        prefer_personal=True,
        smart_rules=None,
        min_alert_score=55,
        rule_options=None,
        platforms=None,
        db_file=DB_FILE,
    ):
        super().__init__()
        self.config = self.normalize_config(config)
        self.interval_min = clamp_int(interval_min, 180, 10, 86400)
        self.interval_max = clamp_int(interval_max, 300, 10, 86400)
        if self.interval_min > self.interval_max:
            self.interval_min, self.interval_max = self.interval_max, self.interval_min
        self.black_words = DEFAULT_BLACK_WORDS if black_words is None else black_words
        self.smart_match = smart_match
        self.prefer_personal = prefer_personal
        self.smart_rules = empty_smart_rules() if smart_rules is None else smart_rules
        self.min_alert_score = min_alert_score
        self.rule_options = default_rule_options()
        if rule_options:
            self.rule_options.update(rule_options)
        self.platforms = platforms or ["xianyu"]
        self.db_file = db_file
        self.hit_store = HitStore(db_file)
        self.platform_risk_cooldowns = {}
        self._running = False
        self.toaster = create_notifier()

    def normalize_config(self, config):
        rows = []
        if not isinstance(config, list):
            return rows
        for row in config[:MAX_MONITOR_ROWS]:
            if not isinstance(row, dict):
                continue
            keyword = limit_text(row.get("keyword", ""), 80)
            if not keyword:
                continue
            min_price = clamp_int(row.get("min_price", 0), 0, 0, MAX_PRICE_VALUE)
            max_price = clamp_int(row.get("max_price", MAX_PRICE_VALUE), MAX_PRICE_VALUE, 0, MAX_PRICE_VALUE)
            if min_price > max_price:
                min_price, max_price = max_price, min_price
            rows.append(
                {
                    "keyword": keyword,
                    "min_price": min_price,
                    "max_price": max_price,
                    "pages": clamp_int(row.get("pages", 1), 1, 1, MAX_SCAN_PAGES),
                }
            )
        return rows

    def emit_log(self, message):
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        self.log_signal.emit(f"[{now}] {message}")

    def shorten_text(self, text, limit=120):
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) <= limit:
            return text
        return f"{text[:limit]}..."

    def normalize_text(self, text):
        return re.sub(r"\s+", "", text.lower())

    def keyword_tokens(self, keyword):
        return [
            token.lower()
            for token in re.split(r"[\s,，、/|+]+", keyword)
            if token.strip()
        ]

    def token_matches_title(self, token, normalized_title):
        gb_match = re.fullmatch(r"(\d+)(gb|g)", token)
        if gb_match:
            size = gb_match.group(1)
            return bool(
                re.search(
                    rf"{size}(gb|g)(内存|统一内存|运存|ram)?",
                    normalized_title,
                )
            )

        aliases = self.keyword_aliases_for_token(token)
        return any(alias in normalized_title for alias in aliases)

    def keyword_aliases_for_token(self, token):
        aliases = {token}
        normalized_token = self.normalize_text(token)
        for alias_group in KEYWORD_ALIAS_GROUPS:
            group_tokens = {
                self.normalize_text(group_token)
                for group_token in alias_group["tokens"]
            }
            if normalized_token in group_tokens:
                aliases.update(
                    self.normalize_text(alias)
                    for alias in alias_group["aliases"]
                )
        return [alias for alias in aliases if alias]

    def title_matches_keyword(self, title, keyword):
        if not self.smart_match:
            return True

        normalized_title = self.normalize_text(title)
        tokens = self.keyword_tokens(keyword)
        if not tokens:
            return True

        return all(self.token_matches_title(token, normalized_title) for token in tokens)

    def item_matches_keyword(self, title, keyword, platform_key="xianyu", item_context=""):
        if platform_key == "xianyu":
            match_text = title
        else:
            match_text = f"{title} {item_context}"
        return self.title_matches_keyword(match_text, keyword)

    def keyword_is_accessory_like(self, keyword):
        normalized_keyword = self.normalize_text(keyword)
        return any(term in normalized_keyword for term in ACCESSORY_LIKE_KEYWORD_TERMS)

    def rule_enabled(self, rule_name):
        return self.rule_options.get(rule_name, True)

    def has_negated_service_context(self, normalized_title, service_term):
        if service_term != "维修":
            return False
        negated_patterns = [
            r"无(任何)?维修(记录|史)?",
            r"没有(任何)?维修(记录|史)?",
            r"没(有)?维修(记录|史)?",
            r"无拆修",
            r"无拆无修",
        ]
        return any(re.search(pattern, normalized_title) for pattern in negated_patterns)

    def has_product_body_context(self, normalized_title):
        if any(term in normalized_title for term in PRODUCT_BODY_CONTEXT_TERMS):
            return True
        if re.search(r"\d{2,4}(g|gb|tb)", normalized_title):
            return True
        if re.search(r"\d{4}年|\d{1,2}月", normalized_title):
            return True
        return False

    def accessory_only_match(self, normalized_title, accessory_term):
        accessory_only_patterns = [
            f"{accessory_term}单出",
            f"单出{accessory_term}",
            f"仅{accessory_term}",
            f"只有{accessory_term}",
            f"只出{accessory_term}",
            f"{accessory_term}一根",
            f"{accessory_term}一个",
            f"{accessory_term}单卖",
            f"单卖{accessory_term}",
            f"不含主机",
            f"不含本体",
            f"无主机",
            f"无本体",
        ]
        return any(pattern in normalized_title for pattern in accessory_only_patterns)

    def service_mismatch_term(self, normalized_title):
        for term in GENERIC_SERVICE_TERMS:
            if term in normalized_title and not self.has_negated_service_context(
                normalized_title,
                term,
            ):
                return term
        return None

    def accessory_mismatch_term(self, normalized_title):
        for term in GENERIC_ACCESSORY_TERMS:
            if term not in normalized_title:
                continue
            if self.accessory_only_match(normalized_title, term):
                return term
            if not self.has_product_body_context(normalized_title):
                return term
        return None

    def generic_type_mismatch_match(self, title, keyword):
        normalized_title = self.normalize_text(title)

        if self.rule_enabled("filter_empty_boxes") and any(
            term in normalized_title for term in GENERIC_EMPTY_BOX_TERMS
        ):
            return "疑似空盒/包装盒，不是商品本体"

        non_functional_term = next(
            (term for term in GENERIC_NON_FUNCTIONAL_TERMS if term in normalized_title),
            None,
        )
        if non_functional_term:
            return f"疑似模型/不可用商品「{non_functional_term}」，不是可正常使用的商品本体"

        if not self.keyword_is_accessory_like(keyword):
            if self.rule_enabled("filter_services"):
                service_term = self.service_mismatch_term(normalized_title)
                if service_term:
                    return f"疑似服务/虚拟内容「{service_term}」，不是商品本体"

            if self.rule_enabled("filter_accessories"):
                accessory_term = self.accessory_mismatch_term(normalized_title)
                if accessory_term:
                    return f"疑似配件「{accessory_term}」，不是商品本体"

        return None

    def product_type_mismatch_match(self, title, keyword, item_context=""):
        if not self.smart_match:
            return None

        normalized_keyword = self.normalize_text(keyword)
        match_text = f"{title} {item_context}" if item_context else title
        normalized_title = self.normalize_text(match_text)

        if re.search(r"(xeon|至强|e[357]\d*)", normalized_keyword):
            board_signals = [
                "x99",
                "x79",
                "主板",
                "芯片组",
                "cpu插槽",
                "lga2011",
                "lga2011v3",
                "双路",
                "单路",
            ]
            compatibility_signals = [
                "支持",
                "可安装",
                "兼容",
                "适用",
                "可上",
                "能上",
                "搭配",
            ]
            cpu_body_signals = [
                "cpu",
                "正式版",
                "散片",
                "拆机",
                "主频",
                "核心数量",
                "线程",
                "热设计功耗",
                "tdp",
                "lga2011-3接口",
                "lga20113接口",
                "从服务器上拆下",
            ]

            if normalized_title.startswith("#x99") or normalized_title.startswith("x99"):
                return "疑似 X99 主板，不是 CPU 本体"

            if "芯片组" in normalized_title or "cpu插槽" in normalized_title:
                return "疑似主板/芯片组说明，不是 CPU 本体"

            cpu_body_signal_count = sum(
                1 for signal in cpu_body_signals if signal in normalized_title
            )
            if cpu_body_signal_count >= 2:
                return None

            has_board_signal = any(signal in normalized_title for signal in board_signals)
            has_compatibility_signal = any(
                signal in normalized_title for signal in compatibility_signals
            )
            if has_board_signal and has_compatibility_signal:
                return "疑似兼容/支持说明，不是 CPU 本体"

        if "macmini" in normalized_keyword:
            if "macstudio" in normalized_title or "macstudio" in normalized_keyword and "macmini" not in normalized_title:
                return "疑似 Mac Studio，不是 Mac mini"

            keyword_wants_pro = "pro" in normalized_keyword
            keyword_wants_max = "max" in normalized_keyword
            if not keyword_wants_pro and re.search(r"m4pro|m4\s*pro", normalized_title):
                return "疑似 M4 Pro 混合型号，不是普通 M4"
            if not keyword_wants_max and re.search(r"m4max|m4\s*max", normalized_title):
                return "疑似 M4 Max 混合型号，不是普通 M4"

            bundle_signals = [
                "显示器",
                "红米4k",
                "键盘",
                "鼠标",
                "扩展坞",
                "底座",
                "支架",
            ]
            bundle_words = ["套装", "整套", "打包", "组合", "一套"]
            if (
                self.rule_enabled("filter_bundles")
                and any(signal in normalized_title for signal in bundle_signals)
                and any(word in normalized_title for word in bundle_words)
            ):
                return "疑似整套打包，不是单台 Mac mini 主机"

        generic_mismatch = self.generic_type_mismatch_match(match_text, keyword)
        if generic_mismatch:
            return generic_mismatch

        return None

    def buyer_intent_match(self, title):
        return next(
            (
                pattern
                for pattern in BUYER_INTENT_PATTERNS
                if re.search(pattern, title, flags=re.IGNORECASE)
            ),
            None,
        )

    def learned_block_match(self, title):
        title_key = normalize_title_key(title)
        blocked_titles = {
            normalize_title_key(blocked_title)
            for blocked_title in self.smart_rules.get("blocked_titles", [])
        }
        if title_key in blocked_titles:
            return "已学习的误报标题"

        return next(
            (
                phrase
                for phrase in self.smart_rules.get("blocked_phrases", [])
                if phrase and phrase in title
            ),
            None,
        )

    def learned_preference_matches(self, title):
        return [
            phrase
            for phrase in self.smart_rules.get("preferred_phrases", [])
            if phrase and phrase in title
        ][:3]

    def evaluate_item_quality(self, title, price, min_price, max_price):
        score = 60
        reasons = []

        price_range = max(max_price - min_price, 1)
        price_position = (price - min_price) / price_range
        if price_position <= 0.25:
            score += 15
            reasons.append("价格靠近低价端")
        elif price_position <= 0.5:
            score += 8
            reasons.append("价格较合适")
        elif price_position >= 0.85:
            score -= 5
            reasons.append("价格接近上限")

        positive_rules = [
            ("自用", 8, "个人自用"),
            ("闲置", 8, "明确闲置"),
            ("没怎么用", 6, "使用少"),
            ("买了没用", 6, "使用少"),
            ("箱说齐全", 6, "箱说齐全"),
            ("配件齐全", 5, "配件齐全"),
            ("无拆修", 6, "无拆修"),
            ("保修", 5, "有保修信息"),
            ("发票", 4, "有发票信息"),
            ("自提", 4, "支持自提"),
            ("可小刀", 3, "可议价"),
        ]
        negative_rules = [
            ("全新未拆", -20, "偏商家/全新货"),
            ("全新未开封", -18, "偏商家/全新货"),
            ("未拆封", -14, "偏商家/全新货"),
            ("批量", -12, "批量货"),
            ("工厂", -12, "工厂货"),
            ("清仓", -12, "清仓货"),
            ("库存", -10, "库存货"),
            ("商用", -6, "偏商用"),
            ("专卖店直供", -25, "偏商家"),
            ("全新未激活", -18, "偏商家/全新货"),
            ("国行正品", -10, "商家式描述"),
            ("官方质检", -15, "商家式描述"),
            ("假一赔三", -20, "商家式描述"),
            ("欢迎咨询", -15, "客服式描述"),
            ("正品保证", -12, "商家式描述"),
            ("正品保障", -12, "商家式描述"),
            ("正品行货", -12, "商家式描述"),
            ("喜欢直接拍", -12, "商家式描述"),
            ("需要直接拍", -12, "商家式描述"),
            ("细节私聊", -10, "商家式描述"),
            ("官方联保", -15, "商家式描述"),
            ("官网直发", -18, "商家式描述"),
            ("做活动剩下", -18, "商家式描述"),
            ("不退不换", -8, "售后风险"),
            ("包邮", -3, "包邮商家感"),
            ("咨询客服", -15, "客服式描述"),
            ("代下", -20, "代下服务"),
            ("回收", -20, "回收/求购"),
            ("求购", -20, "求购"),
        ]

        learned_preferences = self.learned_preference_matches(title)
        if learned_preferences:
            score += min(12, len(learned_preferences) * 4)
            reasons.append(f"符合你的偏好：{'、'.join(learned_preferences)}")

        merchant_penalty_reasons = {
            "偏商家/全新货",
            "商家式描述",
            "客服式描述",
            "包邮商家感",
            "偏商家",
        }
        matched_reasons = set()
        for word, delta, reason in positive_rules + negative_rules:
            if (
                delta < 0
                and not self.rule_enabled("merchant_penalty")
                and reason in merchant_penalty_reasons
            ):
                continue
            if word in title and reason not in matched_reasons:
                score += delta
                reasons.append(reason)
                matched_reasons.add(reason)

        score = max(0, min(100, score))
        if score >= 85:
            level = "强烈关注"
        elif score >= 70:
            level = "优先看看"
        elif score >= 55:
            level = "可看看"
        else:
            level = "低优先级"

        return score, level, "、".join(reasons[:5]) if reasons else "价格命中"

    def load_database(self):
        previous_count = len(self.hit_store.records)
        records = self.hit_store.load()
        if not records and os.path.exists(self.db_file) and previous_count == 0:
            try:
                with open(self.db_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if not isinstance(data, list):
                    self.emit_log("去重数据库内容不是列表，将使用空列表。")
            except Exception as exc:
                self.emit_log(f"读取去重数据库失败，将使用空列表：{exc}")
        return records

    def save_database(self, force=False):
        try:
            self.hit_store.save(force=force)
        except Exception as exc:
            self.error_signal.emit(f"保存去重数据库失败：{exc}")

    def reset_scanned_items(self, items):
        self.hit_store.reset(items)

    def has_seen_hit(self, scanned_key):
        return self.hit_store.has_seen_hit(scanned_key)

    def remember_hit(self, scanned_key):
        return self.hit_store.remember_hit(scanned_key)

    def clear_scanned_items(self):
        self.hit_store.clear()

    def hit_record_key(self, scanned_key):
        return self.hit_store.hit_record_key(scanned_key)

    def stop(self):
        self._running = False
        self.emit_log("收到停止指令，正在结束当前轮询...")

    def interruptible_sleep(self, seconds):
        end_time = time.time() + seconds
        while self._running and time.time() < end_time:
            time.sleep(0.3)

    def is_cdp_available(self, endpoint):
        try:
            with urlopen(f"{endpoint}/json/version", timeout=2) as response:
                return response.status == 200
        except Exception:
            return False

    def load_owned_chrome_session(self):
        data = load_json_file(CHROME_SESSION_FILE, {}, dict)
        if not data:
            return {}
        try:
            pid = int(data.get("pid", 0))
            port = int(data.get("port", 0))
        except Exception:
            return {}
        endpoint = str(data.get("endpoint") or cdp_endpoint(port))
        profile_dir = os.path.abspath(str(data.get("profile_dir", "")))
        if os.path.normcase(profile_dir) != os.path.normcase(os.path.abspath(CHROME_PROFILE_DIR)):
            return {}
        if not is_owned_debug_chrome(pid, CHROME_PROFILE_DIR, port):
            return {}
        return {
            "pid": pid,
            "port": port,
            "endpoint": endpoint,
            "profile_dir": profile_dir,
        }

    def connect_browser(self, playwright):
        session = self.load_owned_chrome_session()
        if not session:
            raise RuntimeError(
                "未找到本软件启动的 Chrome 会话。请点击“一键启动 Chrome”，"
                "不要接管未知 9222 调试浏览器。"
            )

        endpoint = session["endpoint"]
        self.emit_log(f"正在检查本软件 Chrome 调试端口：{endpoint}")
        if not self.is_cdp_available(endpoint):
            raise RuntimeError("本软件 Chrome 调试端口不可用，请重新启动 Chrome。")

        self.emit_log(f"正在通过 CDP 接管本软件 Chrome：{endpoint}")
        return playwright.chromium.connect_over_cdp(endpoint)

    def platform_config(self, platform_key):
        return PLATFORM_CONFIGS.get(platform_key, PLATFORM_CONFIGS["xianyu"])

    def platform_name(self, platform_key):
        return self.platform_config(platform_key)["name"]

    def normalize_item_url(self, item_url, platform_key):
        if not item_url:
            return item_url
        if item_url.startswith("//"):
            return f"https:{item_url}"
        if item_url.startswith("/"):
            return f"{self.platform_config(platform_key)['base_url']}{item_url}"
        return item_url

    def get_item_url_and_id(self, item, platform_key="xianyu"):
        link_tag = item if item.name == "a" else item.find("a")
        if platform_key == "jd":
            sku = item.attrs.get("data-sku")
            if not sku:
                sku_tag = item.find(attrs={"data-sku": True})
                sku = sku_tag.attrs.get("data-sku") if sku_tag else None
            if sku:
                return f"https://item.jd.com/{sku}.html", str(sku)
            link_tag = item if item.name == "a" else item.find(
                "a",
                href=re.compile(r"item\.jd\.com"),
            )
        elif platform_key == "taobao":
            link_tag = None
            if item.name == "a":
                link_tag = item
            if link_tag is None:
                link_tag = item.find("a", attrs={"id": re.compile(r"^item_id_")})
            if link_tag is None:
                link_tag = item.find(
                    "a",
                    href=re.compile(r"(item\.taobao\.com|detail\.tmall\.com|click\.simba\.taobao\.com)"),
                )
        if not link_tag or "href" not in link_tag.attrs:
            return None, None

        item_url = self.normalize_item_url(link_tag["href"], platform_key)
        if platform_key == "jd":
            jd_match = re.search(r"item\.jd\.com/(\d+)\.html", item_url)
            item_id = jd_match.group(1) if jd_match else item_url
        elif platform_key == "taobao":
            item_id = None
            if "id=" in item_url:
                item_id = item_url.split("id=")[-1].split("&")[0]
            if not item_id and link_tag.attrs.get("id", "").startswith("item_id_"):
                item_id = link_tag.attrs["id"].replace("item_id_", "", 1)
            if not item_id:
                item_id = link_tag.attrs.get("data-spm-act-id") or item_url
        else:
            item_id = item_url.split("id=")[-1].split("&")[0] if "id=" in item_url else item_url
        return item_url, item_id

    def extract_title_and_price(self, item):
        text_parts = [part.strip() for part in item.strings if part.strip()]
        title_tag = item.select_one('[class*="title"], [class*="p-name"], [class*="name"]')
        attr_parts = self.extract_attribute_text_parts(item)
        price = self.extract_price_from_text_parts(text_parts + attr_parts)

        if title_tag and price is not None:
            title = title_tag.get_text(" ", strip=True)
            if not title:
                title = self.extract_title_from_attributes(title_tag)
            if title:
                return title, price

        link_tag = item if item.name == "a" else item.find("a")
        if link_tag and price is not None:
            title_attr = self.extract_title_from_attributes(link_tag)
            if title_attr:
                return re.sub(r"\s+", " ", title_attr).strip(), price

        text = item.get_text(" ", strip=True)
        price_match = self.find_price_match(text)
        if not price_match or price is None:
            return None, None

        title = text[: price_match.start()].strip()
        title = re.sub(r"\s+", " ", title)
        return title, price

    def extract_attribute_text_parts(self, item):
        parts = []
        for tag in [item, *item.find_all(True)]:
            for attr_name in (
                "title",
                "aria-label",
                "alt",
                "data-title",
                "data-price",
                "data-value",
                "data-spu",
                "data-sku",
            ):
                attr_value = tag.attrs.get(attr_name)
                if attr_value:
                    parts.append(str(attr_value))
        return parts

    def extract_title_from_attributes(self, tag):
        for attr_name in ("title", "aria-label", "alt", "data-title"):
            attr_value = tag.attrs.get(attr_name)
            if not attr_value:
                continue
            text = re.sub(r"\s+", " ", str(attr_value)).strip()
            if text and not self.find_price_match(text):
                return text
            if text and re.search(r"[A-Za-z\u4e00-\u9fff]", text) and "价格" not in text:
                return text
        return ""

    def extract_item_context(self, item):
        context_parts = [item.get_text(" ", strip=True)]
        for tag in item.find_all(True):
            for attr_name in ("title", "aria-label", "alt", "data-sku", "data-title"):
                attr_value = tag.attrs.get(attr_name)
                if attr_value:
                    context_parts.append(str(attr_value))
        return re.sub(r"\s+", " ", " ".join(context_parts)).strip()

    def extract_price_from_text_parts(self, text_parts):
        for index, part in enumerate(text_parts):
            price_match = self.find_price_match(part)
            if price_match:
                return int(float(price_match.group(1).replace(",", "")))

            if part in ("¥", "￥") and index + 1 < len(text_parts):
                next_part = text_parts[index + 1].replace(",", "")
                if re.fullmatch(r"[0-9]+(?:\.\d+)?", next_part):
                    return int(float(next_part))

        return None

    def find_price_match(self, text):
        text = str(text)
        return re.search(
            r"(?:[¥￥]\s*|价格[:：]?\s*|售价[:：]?\s*)"
            r"([0-9][0-9,]*(?:\.\d+)?)\s*(?:元)?",
            text,
            flags=re.IGNORECASE,
        )

    def find_item_nodes(self, soup, platform_key="xianyu"):
        seen = set()
        items = []
        selectors = self.platform_config(platform_key).get("item_selectors", ITEM_SELECTORS)
        for selector in selectors:
            for item in soup.select(selector):
                item_url, item_id = self.get_item_url_and_id(item, platform_key)
                if not item_id or item_id in seen:
                    continue
                seen.add(item_id)
                items.append(item)
        return items

    def empty_scan_stats(self):
        return {
            "candidate_count": 0,
            "new_count": 0,
            "hit_count": 0,
            "skipped_seen": 0,
            "skipped_black": 0,
            "skipped_parse": 0,
            "skipped_keyword": 0,
            "skipped_type_mismatch": 0,
            "skipped_buyer": 0,
            "skipped_learned": 0,
            "skipped_price": 0,
            "skipped_price_low": 0,
            "skipped_price_high": 0,
            "skipped_low_score": 0,
            "max_hit_page": 0,
            "hits": [],
            "comparison_candidates": [],
        }

    def merge_scan_stats(self, total_stats, page_stats):
        if not page_stats:
            return total_stats
        for key, value in page_stats.items():
            if key == "max_hit_page":
                total_stats[key] = max(total_stats.get(key, 0), value)
            elif key in ("hits", "comparison_candidates"):
                total_stats.setdefault(key, []).extend(value)
            else:
                total_stats[key] = total_stats.get(key, 0) + value
        return total_stats

    def parse_and_check(self, html_content, monitor_item):
        keyword = monitor_item["keyword"]
        min_price = monitor_item["min_price"]
        max_price = monitor_item["max_price"]
        platform_key = monitor_item.get("_platform", "xianyu")
        platform_name = self.platform_name(platform_key)
        is_secondhand_platform = platform_key == "xianyu"

        soup = BeautifulSoup(html_content, "html.parser")
        items = self.find_item_nodes(soup, platform_key)
        stats = self.empty_scan_stats()
        stats["candidate_count"] = len(items)

        if not items:
            self.emit_log("未检测到商品卡片，请检查登录状态、页面结构或风控拦截。")
            return stats

        self.emit_log(f"检测到 {len(items)} 个候选商品卡片。")
        skipped_seen = 0
        skipped_black = 0
        skipped_parse = 0
        skipped_keyword = 0
        skipped_type_mismatch = 0
        skipped_buyer = 0
        skipped_learned = 0
        skipped_price = 0
        skipped_low_score = 0
        new_count = 0
        hit_count = 0

        for item in items:
            if not self._running:
                return stats

            try:
                item_url, item_id = self.get_item_url_and_id(item, platform_key)
                if not item_url or not item_id:
                    continue

                scanned_key = item_id if platform_key == "xianyu" else f"{platform_key}:{item_id}"
                if self.has_seen_hit(scanned_key):
                    skipped_seen += 1
                    continue

                title, price = self.extract_title_and_price(item)
                if not title or price is None:
                    skipped_parse += 1
                    continue
                item_context = self.extract_item_context(item)

                new_count += 1

                if not self.item_matches_keyword(title, keyword, platform_key, item_context):
                    skipped_keyword += 1
                    continue

                type_mismatch = self.product_type_mismatch_match(
                    title,
                    keyword,
                    item_context,
                )
                if type_mismatch:
                    skipped_type_mismatch += 1
                    self.emit_log(
                        f"排除商品类型不匹配：{type_mismatch} | "
                        f"{self.shorten_text(title, 80)}"
                    )
                    continue

                if is_secondhand_platform:
                    buyer_pattern = self.buyer_intent_match(title)
                    if buyer_pattern:
                        skipped_buyer += 1
                        self.emit_log(
                            f"排除求购/回收结果：{self.shorten_text(title, 80)}"
                        )
                        continue

                    learned_block = self.learned_block_match(title)
                    if learned_block:
                        skipped_learned += 1
                        self.emit_log(
                            f"排除已学习误报：命中「{learned_block}」 | "
                            f"{self.shorten_text(title, 80)}"
                        )
                        continue

                    matched_black_word = next(
                        (word for word in self.black_words if word and word in title),
                        None,
                    )
                    if matched_black_word:
                        skipped_black += 1
                        self.emit_log(
                            f"排除低质量结果：命中排除词「{matched_black_word}」 | "
                            f"{self.shorten_text(title, 80)}"
                        )
                        continue

                comparison_candidate = {
                    "keyword": keyword,
                    "platform": platform_key,
                    "platform_name": platform_name,
                    "page_number": monitor_item.get("_page_number", 1),
                    "item_id": item_id,
                    "title": title,
                    "price": price,
                    "score": None,
                    "level": "比价参考",
                    "quality_reason": "用于平台比价，可能超出提醒价格区间",
                    "url": item_url,
                }
                stats.setdefault("comparison_candidates", []).append(comparison_candidate)

                if not (min_price <= price <= max_price):
                    skipped_price += 1
                    if price < min_price:
                        stats["skipped_price_low"] += 1
                    else:
                        stats["skipped_price_high"] += 1
                    continue

                if is_secondhand_platform:
                    score, level, quality_reason = self.evaluate_item_quality(
                        title,
                        price,
                        min_price,
                        max_price,
                    )
                    if score < self.min_alert_score:
                        skipped_low_score += 1
                        self.emit_log(
                            f"低分结果不提醒：{level} {score}分，低于最低提醒评分 "
                            f"{self.min_alert_score} | {self.shorten_text(title, 80)}"
                        )
                        continue
                else:
                    score = 75
                    level = "平台比价"
                    quality_reason = f"{platform_name} 搜索结果"

                hit_count += 1
                stats["max_hit_page"] = max(
                    stats["max_hit_page"],
                    monitor_item.get("_page_number", 1),
                )
                hit = {
                    "keyword": keyword,
                    "platform": platform_key,
                    "platform_name": platform_name,
                    "page_number": monitor_item.get("_page_number", 1),
                    "item_id": item_id,
                    "title": title,
                    "price": price,
                    "score": score,
                    "level": level,
                    "quality_reason": quality_reason,
                    "url": item_url,
                }
                stats.setdefault("hits", []).append(hit)
                self.emit_log(
                    f"命中目标：{platform_name} | {level} {score}分 | {self.shorten_text(title, 100)} | "
                    f"价格：{price} | 理由：{quality_reason} | 链接：{item_url}"
                )
                self.item_found_signal.emit(hit)
                try:
                    self.toaster.show_toast(
                        title=f"{platform_name} {level}：{keyword} {score}分",
                        msg=f"价格：{price} 元\n{self.shorten_text(title, 36)}",
                        duration=8,
                        threaded=True,
                    )
                except Exception as notify_exc:
                    self.emit_log(f"桌面通知失败，已保留界面提醒：{notify_exc}")
                self.remember_hit(scanned_key)
                self.interruptible_sleep(1)
            except Exception as exc:
                self.emit_log(f"解析单条商品异常：{exc}")

        self.emit_log(
            f"本次解析统计：新商品 {new_count} 个，命中 {hit_count} 个，"
            f"已扫描跳过 {skipped_seen} 个，黑名单跳过 {skipped_black} 个，"
            f"关键词不匹配跳过 {skipped_keyword} 个，"
            f"类型不匹配跳过 {skipped_type_mismatch} 个，"
            f"求购/回收跳过 {skipped_buyer} 个，已学习误报跳过 {skipped_learned} 个，"
            f"低分不提醒 {skipped_low_score} 个，"
            f"价格不符跳过 {skipped_price} 个，解析失败跳过 {skipped_parse} 个。"
        )
        stats.update(
            {
                "new_count": new_count,
                "hit_count": hit_count,
                "skipped_seen": skipped_seen,
                "skipped_black": skipped_black,
                "skipped_parse": skipped_parse,
                "skipped_keyword": skipped_keyword,
                "skipped_type_mismatch": skipped_type_mismatch,
                "skipped_buyer": skipped_buyer,
                "skipped_learned": skipped_learned,
                "skipped_price": skipped_price,
                "skipped_low_score": skipped_low_score,
            }
        )
        return stats

    def keyword_type_examples(self, keyword):
        normalized_keyword = self.normalize_text(keyword)
        if re.search(r"(xeon|至强|e[357]\d*)", normalized_keyword):
            return "CPU、处理器"
        if "macmini" in normalized_keyword or "macbook" in normalized_keyword:
            return "主机、16G、256G"
        if "咖啡豆" in normalized_keyword:
            return "手冲、烘焙、阿拉比卡、实物"
        if "苹果手机" in normalized_keyword:
            return "iPhone、型号、容量"
        if "苹果电脑" in normalized_keyword:
            return "MacBook、iMac、Mac mini"
        return "商品本体、型号、容量规格"

    def build_monitor_recommendations(self, monitor_item, stats):
        keyword = monitor_item["keyword"]
        page_count = monitor_item.get("pages", 1)
        candidate_count = stats.get("candidate_count", 0)
        new_count = stats.get("new_count", 0)
        hit_count = stats.get("hit_count", 0)
        type_examples = self.keyword_type_examples(keyword)
        recommendations = []

        if candidate_count == 0:
            recommendations.append("本轮没有抓到商品卡片，优先检查登录状态、页面加载或风控拦截。")
            return recommendations

        if new_count == 0 and stats.get("skipped_seen", 0) > 0:
            recommendations.append("本轮大多是已扫描商品，去重正常；不用频繁清空去重记录。")
            return recommendations

        keyword_skip_ratio = stats.get("skipped_keyword", 0) / max(candidate_count, 1)
        if keyword_skip_ratio >= 0.6:
            recommendations.append(
                f"搜索结果较杂，建议在关键词后加商品类型词，例如 {type_examples}。"
            )

        if stats.get("skipped_type_mismatch", 0) > 0:
            recommendations.append(
                f"出现配件/主板/兼容说明误报，建议关键词写得更像实物，例如 {type_examples}。"
            )

        price_skipped = stats.get("skipped_price", 0)
        if hit_count == 0 and price_skipped >= max(3, new_count * 0.25):
            low_count = stats.get("skipped_price_low", 0)
            high_count = stats.get("skipped_price_high", 0)
            if high_count > low_count:
                recommendations.append("有较多商品高于最高价，想多看结果可适当提高最高价。")
            elif low_count > high_count:
                recommendations.append("有较多商品低于最低价，建议降低最低价或确认是否混入配件。")
            else:
                recommendations.append("价格区间拦下了不少结果，建议根据日志适当放宽区间。")

        noisy_skips = (
            stats.get("skipped_black", 0)
            + stats.get("skipped_buyer", 0)
            + stats.get("skipped_learned", 0)
            + stats.get("skipped_type_mismatch", 0)
        )
        if noisy_skips >= max(3, new_count * 0.2):
            recommendations.append("误报类型偏多，继续用“标记误报”喂几次，过滤会更准。")

        max_hit_page = stats.get("max_hit_page", 0)
        if hit_count > 0 and page_count >= 4 and 0 < max_hit_page <= max(1, page_count // 2):
            suggested_pages = max(1, min(page_count, max_hit_page + 1))
            recommendations.append(
                f"命中集中在前 {max_hit_page} 页，可把扫描页数从 {page_count} 调到 {suggested_pages}，减少等待。"
            )
        elif hit_count >= 3 and page_count == 1:
            recommendations.append("第一页已有多个命中，当前扫描 1 页可以先保持，减少等待和风控风险。")
        elif hit_count > 0 and page_count >= 2 and max_hit_page == page_count and page_count < 10:
            recommendations.append("最后一页仍有命中，可以保持当前页数；想捡漏可小幅增加 1-2 页。")

        if hit_count == 0 and not recommendations:
            recommendations.append(
                f"{keyword} 本轮没有命中；如果连续几轮如此，建议放宽价格或换一个更常见关键词。"
            )

        return recommendations[:3]

    def emit_monitor_recommendations(self, monitor_item, stats):
        recommendations = self.build_monitor_recommendations(monitor_item, stats)
        if not recommendations:
            return

        platform_name = monitor_item.get("_platform_name")
        label = monitor_item["keyword"]
        if platform_name:
            label = f"{label}/{platform_name}"
        self.emit_log(
            f"[智能建议] {label}：{'；'.join(recommendations)}"
        )

    def build_price_comparison(self, monitor_item, platform_hits):
        min_price = monitor_item["min_price"]
        max_price = monitor_item["max_price"]
        platform_best = {}
        for platform_key, hits in platform_hits.items():
            if not hits:
                continue
            reliable_hits = [
                hit
                for hit in hits
                if not self.is_suspicious_price_hit(hit, monitor_item, platform_key)
            ]
            if not reliable_hits:
                continue
            best_hit = min(reliable_hits, key=lambda hit: hit.get("price", 10**12))
            platform_best[platform_key] = best_hit

        if not platform_best:
            return {
                "keyword": monitor_item["keyword"],
                "platforms": {},
                "best_platform": "",
                "best_platform_name": "",
                "best_price": "",
                "best_url": "",
                "price_gap": "",
                "summary": "本轮暂无可比价结果",
            }

        sorted_best = sorted(
            platform_best.items(),
            key=lambda item: item[1].get("price", 10**12),
        )
        best_platform, best_hit = sorted_best[0]
        price_gap = ""
        if len(sorted_best) >= 2:
            price_gap = sorted_best[1][1]["price"] - best_hit["price"]

        platform_prices = {
            platform_key: {
                "platform_name": self.platform_name(platform_key),
                "price": hit["price"],
                "title": hit["title"],
                "url": hit["url"],
                "in_alert_range": min_price <= hit["price"] <= max_price,
            }
            for platform_key, hit in platform_best.items()
        }
        best_platform_name = self.platform_name(best_platform)
        if best_hit["price"] < min_price:
            range_note = "，低于提醒下限，可确认是否为配件或异常低价"
        elif best_hit["price"] > max_price:
            range_note = "，高于提醒上限，仅作为行情参考"
        else:
            range_note = "，在提醒价格区间内"

        if price_gap == "":
            summary = f"{best_platform_name} 当前最低：{best_hit['price']} 元{range_note}"
        else:
            summary = (
                f"{best_platform_name} 当前最低：{best_hit['price']} 元，"
                f"比第二低便宜 {price_gap} 元{range_note}"
            )
        return {
            "keyword": monitor_item["keyword"],
            "platforms": platform_prices,
            "best_platform": best_platform,
            "best_platform_name": best_platform_name,
            "best_price": best_hit["price"],
            "best_url": best_hit["url"],
            "price_gap": price_gap,
            "summary": summary,
            "price_suggestion": self.build_price_suggestion(
                monitor_item,
                best_platform_name,
                best_hit["price"],
            ),
        }

    def round_price_up(self, price):
        step = 50 if price < 1000 else 100
        return ((int(price) + step - 1) // step) * step

    def round_price_down(self, price):
        step = 50 if price < 1000 else 100
        return max(0, (int(price) // step) * step)

    def is_suspicious_price_hit(self, hit, monitor_item, platform_key):
        price = hit.get("price")
        if price is None:
            return True

        keyword = monitor_item.get("keyword", "")
        title = hit.get("title", "")
        quality_reason = hit.get("quality_reason", "")
        text = f"{title} {quality_reason}"

        if self.product_type_mismatch_match(title, keyword, text):
            return True

        if platform_key != "xianyu" and price < max(1, monitor_item.get("min_price", 0)) * 0.2:
            return True

        keyword_floor_patterns = [
            (r"mac\s*mini|macmini", 1000),
            (r"macbook|苹果电脑", 1000),
            (r"iphone|苹果手机", 300),
            (r"xeon|至强|e[357]\d*", 20),
        ]
        normalized_keyword = self.normalize_text(keyword)
        for pattern, floor_price in keyword_floor_patterns:
            if re.search(pattern, normalized_keyword, flags=re.IGNORECASE) and price < floor_price:
                return True

        return False

    def build_price_suggestion(self, monitor_item, platform_name, best_price):
        min_price = monitor_item["min_price"]
        max_price = monitor_item["max_price"]
        keyword = monitor_item["keyword"]

        if best_price > max_price:
            suggested_max = self.round_price_up(best_price * 1.05)
            if suggested_max <= max_price:
                suggested_max = self.round_price_up(best_price)
            return {
                "keyword": keyword,
                "current_min_price": min_price,
                "current_max_price": max_price,
                "suggested_min_price": min_price,
                "suggested_max_price": suggested_max,
                "best_price": best_price,
                "platform_name": platform_name,
                "action": "raise_max",
                "reason": (
                    f"{platform_name} 当前最低 {best_price} 元，高于最高价 {max_price} 元，"
                    f"建议把最高价调到 {suggested_max} 元再观察。"
                ),
            }

        if best_price < min_price:
            suggested_min = self.round_price_down(best_price * 0.95)
            return {
                "keyword": keyword,
                "current_min_price": min_price,
                "current_max_price": max_price,
                "suggested_min_price": suggested_min,
                "suggested_max_price": max_price,
                "best_price": best_price,
                "platform_name": platform_name,
                "action": "lower_min",
                "reason": (
                    f"{platform_name} 当前最低 {best_price} 元，低于最低价 {min_price} 元，"
                    f"建议把最低价调到 {suggested_min} 元并确认是否混入配件。"
                ),
            }

        return None

    def emit_price_comparison(self, monitor_item, platform_hits):
        comparison = self.build_price_comparison(monitor_item, platform_hits)
        self.emit_log(f"[比价] {monitor_item['keyword']}：{comparison['summary']}")
        suggestion = comparison.get("price_suggestion")
        if suggestion:
            self.emit_log(f"[智能价格] {suggestion['reason']}")
        self.comparison_signal.emit(comparison)

    def build_search_urls(self, keyword, platform_key="xianyu"):
        encoded_keyword = quote_plus(keyword)
        return [
            template.format(query=encoded_keyword, keyword=encoded_keyword)
            for template in self.platform_config(platform_key).get(
                "search_url_templates",
                SEARCH_URL_TEMPLATES,
            )
        ]

    def goto_search_page(self, page, keyword, platform_key="xianyu"):
        last_error = None
        platform_name = self.platform_name(platform_key)
        for search_url in self.build_search_urls(keyword, platform_key):
            if not self._running:
                return False

            try:
                self.emit_log(f"正在打开{platform_name}搜索页：{search_url}")
                page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                return True
            except Exception as exc:
                last_error = exc
                self.emit_log(f"搜索页打开失败：{search_url} | {exc}")

        raise RuntimeError(f"所有搜索页地址均打开失败：{last_error}")

    def apply_personal_filter(self, page):
        if not self.prefer_personal:
            return

        try:
            self.emit_log("正在应用筛选：个人闲置")
            personal_filter = page.get_by_text("个人闲置", exact=True).last
            if personal_filter.count() == 0:
                self.emit_log("未找到“个人闲置”筛选项，继续扫描当前结果。")
                return

            personal_filter.click(timeout=5000)
            page.wait_for_timeout(random.randint(1200, 2200))
            self.wait_for_item_cards(page, timeout=10000, platform_key="xianyu")
        except Exception as exc:
            self.emit_log(f"应用“个人闲置”筛选失败，继续扫描当前结果：{exc}")

    def detect_login_or_verification_page(self, page, platform_key="xianyu"):
        try:
            url = page.url
            title = page.title()
        except Exception:
            return None

        page_hint = self.normalize_text(f"{url} {title}")
        blocked_terms = [
            "passport.jd.com",
            "login.taobao.com",
            "login.tmall.com",
            "login",
            "captcha",
            "verify",
            "验证",
            "安全检测",
            "欢迎登录",
            "登录",
        ]
        if any(term in page_hint for term in blocked_terms):
            return (
                f"{self.platform_name(platform_key)} 当前跳到登录/验证页，"
                "请在被接管的 Chrome 里完成登录或验证后再继续。"
                f"URL：{url} | 标题：{title}"
            )
        return None

    def risk_cooldown_rounds(self, platform_key):
        return PLATFORM_RISK_COOLDOWN_ROUNDS.get(platform_key, 1)

    def handle_platform_risk_block(self, platform_key, blocked_message):
        current_rounds = self.platform_risk_cooldowns.get(platform_key, 0)
        cooldown_rounds = self.risk_cooldown_rounds(platform_key)
        if current_rounds < cooldown_rounds:
            self.platform_risk_cooldowns[platform_key] = cooldown_rounds
            self.emit_log(blocked_message)
            self.emit_log(
                f"[风控保护] 已暂停{self.platform_name(platform_key)}扫描 "
                f"{cooldown_rounds} 轮，避免反复触发账号风险。"
            )

    def consume_platform_risk_cooldown(self, platform_key):
        remaining_rounds = self.platform_risk_cooldowns.get(platform_key, 0)
        if remaining_rounds <= 0:
            return False

        self.emit_log(
            f"[风控保护] 跳过{self.platform_name(platform_key)}本轮扫描，"
            f"剩余冷却 {remaining_rounds} 轮。"
        )
        if remaining_rounds <= 1:
            self.platform_risk_cooldowns.pop(platform_key, None)
        else:
            self.platform_risk_cooldowns[platform_key] = remaining_rounds - 1
        return True

    def wait_for_item_cards(self, page, timeout=15000, platform_key="xianyu"):
        blocked_message = self.detect_login_or_verification_page(page, platform_key)
        if blocked_message:
            self.handle_platform_risk_block(platform_key, blocked_message)
            return False

        try:
            selectors = self.platform_config(platform_key).get("item_selectors", ITEM_SELECTORS)
            ready_selector = ", ".join(selectors)
            page.wait_for_selector(ready_selector, state="attached", timeout=timeout)
            count = page.locator(ready_selector).count()
            self.emit_log(f"页面商品流已加载，当前可见候选节点：{count} 个。")
            return True
        except Exception as exc:
            blocked_message = self.detect_login_or_verification_page(page, platform_key)
            if blocked_message:
                self.handle_platform_risk_block(platform_key, blocked_message)
                return False

            self.emit_log(
                "等待商品卡片超时，当前页面可能仍在加载、登录失效或页面结构改变。"
                f"URL：{redact_sensitive_text(page.url)} | 标题：{redact_sensitive_text(page.title())} | {exc}"
            )
            return False

    def url_with_query_param(self, url, key, value):
        parsed = urlparse(url)
        query_items = dict(parse_qsl(parsed.query, keep_blank_values=True))
        query_items[key] = str(value)
        return urlunparse(parsed._replace(query=urlencode(query_items)))

    def query_param_value(self, url, key):
        parsed = urlparse(url)
        query_items = dict(parse_qsl(parsed.query, keep_blank_values=True))
        return query_items.get(key)

    def taobao_current_page_number(self, page):
        try:
            current_label = page.locator(
                "div[class*='pgWrap'] button.next-current"
            ).last.get_attribute("aria-label", timeout=3000)
            if current_label:
                current_match = re.search(r"第\s*(\d+)\s*页", current_label)
                if current_match:
                    return int(current_match.group(1))
        except Exception:
            pass

        try:
            page_value = self.query_param_value(page.url, "page")
            return int(page_value) if page_value and page_value.isdigit() else None
        except Exception:
            return None

    def click_taobao_page_button(self, page, page_number):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(random.randint(800, 1400))
        page_button = page.locator(
            (
                "div[class*='pgWrap'] button.next-pagination-item"
                f"[aria-label^='第{page_number}页']"
            )
        ).last
        if page_button.count() == 0:
            page_button = page.locator(
                (
                    "div[class*='pgWrap'] button.next-pagination-item"
                    f"[aria-label*='第{page_number}页']"
                )
            ).last
        if page_button.count() == 0:
            return False

        page_button.click(timeout=5000)
        page.wait_for_timeout(random.randint(1800, 3000))
        return True

    def goto_taobao_result_page(self, page, page_number):
        if page_number <= 1:
            return True

        try:
            self.emit_log(f"正在跳转到淘宝第 {page_number} 页...")
            if not self.click_taobao_page_button(page, page_number):
                self.emit_log(f"未找到淘宝第 {page_number} 页按钮，停止继续翻页。")
                return False

            current_page = self.taobao_current_page_number(page)
            if current_page != page_number:
                self.emit_log(
                    f"淘宝页码校验失败：目标第 {page_number} 页，"
                    f"当前第 {current_page or '未知'} 页，停止继续翻页。"
                )
                return False

            return self.wait_for_item_cards(
                page,
                timeout=10000,
                platform_key="taobao",
            )
        except Exception as exc:
            self.emit_log(f"淘宝第 {page_number} 页跳转失败：{exc}")
            return False

    def goto_result_page(self, page, page_number, platform_key="xianyu"):
        if page_number <= 1:
            return True
        if platform_key == "taobao":
            return self.goto_taobao_result_page(page, page_number)

        for attempt in range(3):
            try:
                input_box = page.locator(PAGINATION_INPUT_SELECTOR).last
                confirm_button = page.locator(PAGINATION_CONFIRM_SELECTOR).last
                if input_box.count() == 0 or confirm_button.count() == 0:
                    self.emit_log("未找到分页跳转控件，本关键词只能扫描当前页。")
                    return False

                self.emit_log(f"正在跳转到第 {page_number} 页...")
                input_box.fill(str(page_number))
                confirm_button.click()
                page.wait_for_timeout(random.randint(1200, 2200))
                result = self.wait_for_item_cards(page, timeout=10000, platform_key=platform_key)
                if result:
                    return True
                if attempt < 2:
                    self.emit_log(f"第 {page_number} 页商品流加载未确认，第{attempt+2}/3次重试...")
                    page.wait_for_timeout(random.randint(1500, 3000))
            except Exception as exc:
                if attempt < 2:
                    self.emit_log(f"跳转到第 {page_number} 页失败（{exc}），第{attempt+2}/3次重试...")
                    page.wait_for_timeout(random.randint(1000, 2500))
                else:
                    self.emit_log(f"跳转到第 {page_number} 页失败（已重试3次）：{exc}")

        return False

    def scan_loaded_page(self, page, monitor_item, page_number):
        self.emit_log(f"正在解析第 {page_number} 页商品...")

        platform_key = monitor_item.get("_platform", "xianyu")
        blocked_message = self.detect_login_or_verification_page(page, platform_key)
        if blocked_message:
            self.handle_platform_risk_block(platform_key, blocked_message)
            return self.empty_scan_stats()

        if platform_key != "xianyu":
            self.emit_log("正在触发平台商品流懒加载...")
            for _ in range(2):
                if not self._running:
                    return self.empty_scan_stats()
                page.mouse.wheel(0, random.randint(700, 1200))
                time.sleep(random.uniform(0.4, 1.0))

        if not self.wait_for_item_cards(page, platform_key=platform_key):
            self.emit_log("商品流未确认加载，已跳过本页解析，避免把登录/验证页误判为商品。")
            return self.empty_scan_stats()

        scroll_rounds = 3 if platform_key != "xianyu" else 2
        for _ in range(scroll_rounds):
            if not self._running:
                return self.empty_scan_stats()
            page.mouse.wheel(0, random.randint(300, 600))
            time.sleep(random.uniform(0.5, 1.5))

        if not self.wait_for_item_cards(page, timeout=5000, platform_key=platform_key):
            self.emit_log("二次加载校验失败，已跳过本页解析。")
            return self.empty_scan_stats()
        page_monitor_item = dict(monitor_item)
        page_monitor_item["_page_number"] = page_number
        page_stats = self.parse_and_check(page.content(), page_monitor_item)
        return page_stats or self.empty_scan_stats()

    @pyqtSlot()
    def run(self):
        self._running = True
        self.reset_scanned_items(self.load_database())
        self.emit_log("Worker 已启动，准备接管本软件启动的 Chrome")
        page = None
        browser = None

        try:
            with sync_playwright() as p:
                browser = self.connect_browser(p)
                if not browser.contexts:
                    self.error_signal.emit("未找到浏览器上下文，请确认已通过本软件启动 Chrome。")
                    return

                context = browser.contexts[0]
                page = context.new_page()
                page.set_default_timeout(10000)
                page.set_default_navigation_timeout(15000)
                page.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
                )

                while self._running:
                    self.emit_log("正在刷新数据...")

                    for monitor_item in self.config:
                        if not self._running:
                            break

                        keyword = monitor_item["keyword"]
                        page_count = monitor_item.get("pages", 1)
                        selected_platforms = [
                            platform
                            for platform in self.platforms
                            if platform in PLATFORM_CONFIGS
                        ] or ["xianyu"]
                        platform_names = "、".join(
                            self.platform_name(platform)
                            for platform in selected_platforms
                        )
                        self.emit_log(
                            f"正在监测：{keyword}，价格："
                            f"{monitor_item['min_price']}-{monitor_item['max_price']} 元，"
                            f"扫描前 {page_count} 页，平台：{platform_names}"
                        )

                        platform_hits = {}
                        for platform_key in selected_platforms:
                            if not self._running:
                                break
                            if self.consume_platform_risk_cooldown(platform_key):
                                platform_hits[platform_key] = []
                                continue

                            platform_name = self.platform_name(platform_key)
                            platform_monitor_item = dict(monitor_item)
                            platform_monitor_item["_platform"] = platform_key
                            platform_monitor_item["_platform_name"] = platform_name
                            monitor_stats = self.empty_scan_stats()
                            platform_hits[platform_key] = monitor_stats["hits"]

                            try:
                                self.emit_log(f"正在监测平台：{platform_name}")
                                if not self.goto_search_page(page, keyword, platform_key):
                                    continue

                                if platform_key == "xianyu":
                                    self.apply_personal_filter(page)

                                for page_number in range(1, page_count + 1):
                                    if not self._running:
                                        break

                                    if not self.goto_result_page(
                                        page,
                                        page_number,
                                        platform_key,
                                    ):
                                        break

                                    page_stats = self.scan_loaded_page(
                                        page,
                                        platform_monitor_item,
                                        page_number,
                                    )
                                    self.merge_scan_stats(monitor_stats, page_stats)
                                    self.interruptible_sleep(random.uniform(2, 5))

                                platform_hits[platform_key] = monitor_stats.get(
                                    "comparison_candidates",
                                    monitor_stats.get("hits", []),
                                )
                                if self._running:
                                    self.emit_monitor_recommendations(
                                        platform_monitor_item,
                                        monitor_stats,
                                    )
                            except Exception as exc:
                                self.emit_log(f"{platform_name} 扫描失败，继续其他平台：{exc}")

                        if self._running:
                            self.emit_price_comparison(monitor_item, platform_hits)

                    if self._running:
                        self.save_database()
                        sleep_time = random.randint(self.interval_min, self.interval_max)
                        self.emit_log(f"本轮扫描结束，下一轮将在 {sleep_time} 秒后进行...")
                        self.interruptible_sleep(sleep_time)
        except Exception as exc:
            self.error_signal.emit(f"爬虫线程异常：{exc}")
        finally:
            if page:
                try:
                    page.close()
                except Exception:
                    pass
            if browser:
                try:
                    browser.close()
                except Exception:
                    pass
            self.save_database()
            self._running = False
            self.emit_log("Worker 已停止。")
            self.finished_signal.emit()



__all__ = ["XianyuMonitorWorker"]
