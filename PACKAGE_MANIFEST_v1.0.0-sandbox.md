# PACKAGE MANIFEST — ACS v1.0.0-sandbox

---

## 版本

**ACS v1.0.0-sandbox（生产前安全冻结版）**

---

## 核心源码目录

```
acs/
├── core/           # task_model, result_model, error_model
├── fetcher/        # http_client, response_classifier
├── parser/         # parser_engine, css_parser, xpath_parser, json_parser, jsonld_parser, fallback_parser, ai_parser
├── schema/         # normalizer, validator, quality_score
├── storage/        # dedup, checkpoint, export_json
├── observability/  # logger, ai_call_audit, cost_report
├── provider/       # provider_config, ai_client, openai_compatible_client, provider_errors, live_ai_smoke
├── evaluation/     # on_mode_readiness, readiness_score, site_readiness_report, risk_classifier, canary_plan, rollback_plan, manual_approval_gate
├── ops/            # scheduler, cron_export, health_check, log_rotation, backup_manager, data_retention, release_checklist, canary_runner, canary_monitor, rollback_executor
├── web/            # app.py, auth.py, safe_actions.py, charts.py, site_routes.py, health_routes.py, templates/
├── sites/          # site_config, site_registry, site_metrics
├── scripts/        # run_ai_shadow_smoke, run_acs_shadow_chain_smoke, run_shadow_batch
├── adapter.py      # ACS shadow adapter
└── dashboard/      # report_builder, review_queue_view, cost_view, shadow_view, structure_view, cli_dashboard

universal_core.py   # 旧流程核心（不修改）
main.py             # 入口（不破坏原有功能）
```

---

## UI 静态文件

```
acs_ui/
├── index.html      (397 lines / 18.7 KB)
├── styles.css      (227 lines / 11.1 KB)
└── app.js          (73 lines / 2.4 KB)
```

---

## 配置文件

```
.env.example               # 环境变量示例（不含真实 Key）
.gitignore                  # Git 忽略配置
```

---

## 测试文件（9 个目录）

```
tests/
├── test_fetcher.py
├── test_parser.py
├── test_schema.py
├── test_dedup.py
├── test_checkpoint.py
├── test_web_*.py           # 4 files
├── test_site_*.py          # 2 files
├── test_scheduler.py
├── test_health_check.py
├── test_log_rotation.py
├── test_backup_manager.py
├── test_data_retention.py
├── test_release_checklist.py
├── test_*readiness*.py     # 4 files
├── test_canary_*.py        # 3 files
├── test_rollback_*.py
├── test_manual_approval_gate.py
└── ...
```

---

## 文档文件

```
RELEASE_NOTES_v1.0.0-sandbox.md     # 发布说明
README_RELEASE_v1.0.0-sandbox.md    # 使用说明
SAFETY_BOUNDARIES_v1.0.0-sandbox.md # 安全边界说明
PACKAGE_MANIFEST_v1.0.0-sandbox.md  # 本文件（打包清单）
```

---

## 不应打包的内容

以下内容 **必须排除**，不得进入发行包：

```
# 密钥与凭据
.env
.env.smoke
任何包含真实 API Key 的文件

# Cookie / Token / Authorization
任何包含认证凭据的文件

# 运行时生成
acs_shadow_logs/*.jsonl
acs_shadow_logs/*.json
logs/*.log
logs/*.jsonl
acs_data/*.db
reports/daily/
reports/weekly/

# 构建与缓存
__pycache__/
.pytest_cache/
dist/
build/
*.pyc
*.pyo

# IDE
.vscode/
.idea/
```

---

## .gitignore 覆盖率确认

| 模式 | 是否覆盖 |
| --- | --- |
| `.env` | ✅ |
| `.env.smoke` | ✅ |
| `logs/` | ✅ |
| `acs_shadow_logs/` | ✅ |
| `acs_data/` | ✅ |
| `reports/` | ✅ |
| `__pycache__/` | ✅ （Git 默认） |
