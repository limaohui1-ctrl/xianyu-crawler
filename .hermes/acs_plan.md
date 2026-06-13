# ACS Phase 1 + Phase 2 实现计划

> **目标**: 将现有爬虫从脚本式结构升级为工程化、多解析器、可断点续爬、可去重、可统一输出 schema 的基础版本。

**架构原则**: 
- 所有新模块放在 `acs/` 包下，独立于现有代码
- 通过 adapter 模式桥接到现有 `UniversalCollector` 
- 不修改现有 `universal_core.py`、`core_checkpoint.py` 等核心文件
- 新增模块职责单一，可独立测试

**技术栈**: Python 3.11+, `dataclasses`, `hashlib`, `json`, `re`, `urllib`, `lxml`, `bs4`

---

## 执行顺序

### Batch 1: 数据模型 (无依赖)
1. `acs/core/task_model.py` — 任务数据模型
2. `acs/core/result_model.py` — 统一结果 schema
3. `acs/core/error_model.py` — 错误分类模型

### Batch 2: 采集层 (依赖 Batch 1)
4. `acs/fetcher/http_client.py` — HTTP 客户端
5. `acs/fetcher/response_classifier.py` — 响应分类

### Batch 3: 解析引擎 (依赖 Batch 1)
6. `acs/parser/parser_engine.py` — 多解析器编排
7. `acs/parser/css_parser.py` — CSS 解析器
8. `acs/parser/xpath_parser.py` — XPath 解析器
9. `acs/parser/json_parser.py` — JSON 解析器
10. `acs/parser/jsonld_parser.py` — JSON-LD 解析器
11. `acs/parser/fallback_parser.py` — 兜底解析器

### Batch 4: Schema 层 (依赖 Batch 1)
12. `acs/schema/normalizer.py` — 字段规范化
13. `acs/schema/validator.py` — Schema 验证
14. `acs/schema/quality_score.py` — 质量评分

### Batch 5: 存储层 (依赖 Batch 1-4)
15. `acs/storage/dedup.py` — 去重
16. `acs/storage/checkpoint.py` — 断点续爬
17. `acs/storage/export_json.py` — JSON 导出

### Batch 6: 可观测性 (无依赖)
18. `acs/observability/logger.py` — 结构化日志

### Batch 7: 测试
19-23. 测试文件

### Batch 8: 集成 adapter
24. `acs/adapter.py` — 桥接现有代码的 adapter

---

## 全部 23 个文件的实现将在本会话中完成
