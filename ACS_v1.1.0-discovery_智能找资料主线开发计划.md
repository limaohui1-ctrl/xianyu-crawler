# ACS v1.1.0-discovery — 智能找资料主线开发计划

---

## 1. 为什么当前项目主线需要调整

| 问题 | 现状 | 影响 |
| --- | --- | --- |
| 主界面被安全控制台占据 | 首页显示 Phase/Canary/Rollback/pytest | 普通用户看不懂 |
| 核心流程缺失 | 无"关键词→发现来源"的能力 | 用户必须自己找 URL |
| 产品定位偏离 | 更像安全审计后台而非资料采集工具 | 用户预期落差大 |
| shadow/sandbox/readiness 占据主交互 | 20 项诊断指标霸屏 | 采集功能的入口被淹没 |

> **根因**：安全/审计/readiness/canary 是**底层保护机制**，不应成为**用户主流程**。

---

## 2. 已有能力保留为底层支撑

| 已有模块 | 在新架构中的角色 |
| --- | --- |
| core/task_model, result_model, error_model | 采集任务数据模型 |
| fetcher/http_client | 执行实际 HTTP 请求 |
| parser/css_parser, xpath_parser, json_parser | 解析采集到的页面 |
| schema/normalizer, validator, quality_score | 字段清洗 + 完整度评分 |
| storage/dedup, checkpoint, export_json | 去重、断点、导出 |
| observability/logger, ai_call_audit | 日志 + AI 成本审计 |
| evaluation/readiness, canary, rollback | 后台健康评估（降级到高级设置） |
| ops/health_check, release_checklist | 运维诊断（降级到高级设置） |
| acs_ui/index.html | 桌面端控制台（已重构为资料采集助手 UI） |

> **全部保留。** 仅 UI 层重新编排优先级。

---

## 3. 新核心主线：智能找资料

```
用户输入主题/关键词
  → 系统生成搜索查询
    → 通过可发现的渠道搜索候选来源
      → 合规过滤（排除需登录/验证码/反爬的站点）
        → 相关度排序
          → 用户确认候选来源
            → 加入采集任务
              → 自动采集
                → 清洗整理
                  → 表格预览
                    → 导出 Excel / JSON / Markdown / PDF
```

---

## 4. 新 UI 主流程

```
首页 → 智能找资料 → 候选来源确认 → 采集结果 → 导出
              ↓
         新建采集（已有）
```

### 首页按钮顺序（调整后）

| 顺序 | 按钮 | 目标 |
| --- | --- | --- |
| 1 | 🧠 智能找资料 | 输入主题，自动发现来源 |
| 2 | 📋 新建采集任务 | 手动创建采集任务 |
| 3 | 📂 导入 URL 文件 | 导入已有 URL 列表 |
| 4 | 📊 查看采集结果 | 表格预览 |
| 5 | 📥 导出资料 | Excel/JSON/MD/PDF |
| 6 | 🔧 高级设置 | 诊断/合规检查（折叠） |

---

## 5. 新增页面

### 5.1 智能找资料

```
┌──────────────────────────────────────────┐
│  🧠 智能找资料                             │
├──────────────────────────────────────────┤
│  资料主题  [园区废气治理案例_______]        │
│  关键词    [VOCs, 活性炭, 废气治理, 整改报告] │
│  资料类型  [网页资料 ▾]                     │
│  预计数量  [50]                            │
│  ───────────────────────────────────      │
│  [开始搜索]                                │
│                                           │
│  ⓘ 系统将通过公开、合规渠道发现候选来源。       │
│    不会绕过登录、验证码或访问控制。             │
└──────────────────────────────────────────┘
```

### 5.2 候选来源确认

```
┌──────────────────────────────────────────────┐
│  候选来源确认  搜索结果: 32 条                  │
├──────────────────────────────────────────────┤
│  [全选] [反选] [仅选可采集] [加入采集任务]      │
│                                              │
│  ☑ │标题                  │来源       │相关度│风险│
│  ──┼──────────────────────┼───────────┼─────┼───│
│  ☑ │园区VOCs治理典型案例   │epb.gov.cn │ 92% │ 低 │
│  ☑ │活性炭吸附技术应用指南  │mee.gov.cn │ 88% │ 低 │
│  ☑ │废气治理整改报告汇编    │zhbb.gov.cn│ 85% │ 低 │
│  ☐ │XXX环保设备供应商      │example.com│ 71% │ 中 │
│  ☐ │XXX公司治理方案.pdf    │xxx.co     │ 65% │ 高 │
│  ✕  │付费资料平台页面       │paywall.cn │ 40% │禁止│
│  ──┴──────────────────────┴───────────┴─────┴───│
│                                              │
│  已选 18 条  |  [加入采集任务]                 │
└──────────────────────────────────────────────┘
```

---

## 6. 新增模块

```
acs/discovery/
├── __init__.py
├── query_builder.py          # 主题+关键词 → 搜索查询
├── search_provider.py        # 抽象搜索接口
├── mock_search_provider.py   # Mock 搜索（开发用）
├── source_discovery.py       # 编排发现流程
├── sitemap_discovery.py      # sitemap.xml 解析
├── rss_discovery.py          # RSS/Atom 解析
├── candidate_url.py          # 候选来源数据模型
├── candidate_store.py        # 候选来源持久化
├── compliance_filter.py      # 合规过滤
├── relevance_ranker.py       # 相关度排序
├── discovery_report.py       # 发现报告
└── templates/
    └── query_templates.json  # 资料类型→搜索模板
```

---

## 7. 核心数据模型

### CandidateURL

```python
@dataclass
class CandidateURL:
    """一条自动发现的候选资料来源"""
    candidate_id: str
    url: str
    title: str
    snippet: str
    source_domain: str
    source_type: str          # web_page / pdf / api / csv / rss
    discovery_method: str     # search / sitemap / rss / api / manual
    matched_keywords: list
    estimated_relevance: float  # 0-100
    compliance_status: str    # ok / needs_confirm / blocked
    risk_level: str           # low / medium / high / forbidden
    reason: str               # 为什么被标记为当前状态
    selected: bool            # 用户是否已确认加入采集
    discovered_at: str
```

### DiscoveryQuery

```python
@dataclass
class DiscoveryQuery:
    """用户输入的找资料请求"""
    topic: str
    keywords: list
    source_type: str
    max_results: int
    language: str
    exclude_commercial: bool
```

---

## 8. 合规过滤逻辑

```python
# compliance_filter.py

BLOCKED_DOMAINS = {
    # 已知受反爬保护的商业平台
    "amazon.com": "blocked_403",
    "walmart.com": "blocked_403",
    "bestbuy.com": "blocked_403",
    "homedepot.com": "blocked_403",
    "ebay.com": "blocked_403",
}

BLOCKED_PATTERNS = [
    # 需要认证的 URL 模式
    r"/login", r"/signin", r"/auth",
    r"token=", r"session=", r"cookie=",
    r"captcha", r"/paywall", r"/subscribe",
]

def check(url: str) -> tuple[str, str]:
    """返回 (compliance_status, reason)"""
    # 检查域名黑名单
    for domain, reason in BLOCKED_DOMAINS.items():
        if domain in url:
            return ("blocked", f"commercial platform: {reason}")
    # 检查 URL 模式
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, url):
            return ("blocked", f"auth/paywall pattern: {pattern}")
    # 默认通过
    return ("ok", "")
```

> **关键**：blocked 的候选来源永不自动采集，只在表格中标记为 ✕ 禁止。

---

## 9. 候选 URL 确认流程

```
SourceDiscovery.discover(query)
        │
        ▼
  [候选 URL 列表]  (raw, unfiltered)
        │
        ▼
  ComplianceFilter.check()
        │
        ├── ok → "可采集", risk=low
        ├── needs_confirm → "需用户确认", risk=medium/high  
        └── blocked → "禁止采集", risk=forbidden
        │
        ▼
  RelevanceRanker.score()
        │
        ▼
  CandidateStore.save()
        │
        ▼
  [用户确认页面]  (候选来源表格)
        │
        ▼
  [加入采集任务]  (仅 selected=True 的条目)
```

---

## 10. 与现有采集任务衔接

```
候选来源确认 → 加入采集任务 → run_shadow_batch.py
                                    │
                            acs_shadow_logs/acs_shadow.jsonl
                                    │
                            parser_engine → normalizer → quality_score
                                    │
                            采集结果表格 → 导出
```

已选中的 `CandidateURL` 直接写入 `urls_*.txt` 文件，然后调用现有 `acs.scripts.run_shadow_batch` 执行采集。

---

## 11. P0 / P1 / P2 优先级

### P0：智能找资料

| 模块 | 说明 |
| --- | --- |
| query_builder.py | 主题+关键词 → 搜索查询 |
| mock_search_provider.py | Mock 搜索返回候选结果 |
| source_discovery.py | 编排发现流程 |
| candidate_url.py | 数据模型 |
| compliance_filter.py | 合规过滤 |
| relevance_ranker.py | 相关度评分 |
| candidate_store.py | 候选来源持久化 |
| "智能找资料" 页面 | UI |
| "候选来源确认" 页面 | UI |
| 8 个测试文件 | pytest |

### P1：资料采集与整理增强

| 模块 | 说明 |
| --- | --- |
| 字段规则 UI | 已有 → 保持 |
| 采集结果表格 | 已有 → 保持 |
| 导出报告 UI | 已有 → 保持 |
| CSV/Excel 导入 | 已有 → 保持 |

### P2：安全/审计/sandbox

| 模块 | 说明 |
| --- | --- |
| readiness | 降级到高级设置 |
| canary sandbox | 降级到高级设置 |
| rollback | 降级到高级设置 |
| health_check | 降级到高级设置 |
| release_checklist | 降级到高级设置 |

---

## 12. 测试计划

| 测试文件 | 覆盖 |
| --- | --- |
| test_query_builder.py | 主题/关键词→查询构造 |
| test_mock_search_provider.py | Mock 搜索返回正确格式 |
| test_source_discovery.py | 发现流程编排 |
| test_candidate_url.py | 数据模型序列化 |
| test_candidate_store.py | CRUD 操作 |
| test_compliance_filter.py | blocked/ok/needs_confirm 判定 |
| test_relevance_ranker.py | 相关度评分排序 |
| test_discovery_report.py | 报告生成 |

**所有测试必须**：mock only，不访问真实网络，不泄露 Key。

---

## 13. 验收标准

| 标准 | 说明 |
| --- | --- |
| 搜索发现 | 输入主题/关键词后，系统返回候选来源列表 |
| 合规过滤 | blocked 来源标记为禁止，不进入采集 |
| 用户确认 | 用户勾选确认后，候选来源加入采集任务 |
| 采集衔接 | 确认的来源能自动进入 shadow batch 采集 |
| UI 流程 | 首页→智能找资料→候选确认→采集结果→导出 流程完整 |
| 安全不变 | ACS_MODE=shadow 不变，canary 不执行真实站，403/401 不绕过 |
| 测试通过 | pytest ≥ 原有 529 + 新增 8 个文件全部通过 |
| 无泄露 | API Key/Cookie/Token 零泄露 |
```

## 14. 最终判断

**从现在开始，ACS 项目主线是"资料采集助手：输入主题，自动发现资料来源，确认后采集并导出"。** 

底层 shadow/safety/readiness/canary/rollback 全部保留为后台保护机制，不再担任 UI 主流程。
