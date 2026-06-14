# RELEASE NOTES — ACS v1.0.0-sandbox

---

## 版本

**ACS v1.0.0-sandbox**

## 发布日期

2026-06-14

## 当前状态

```
生产前安全冻结版 / Sandbox Release / 内部测试发布版
ACS_MODE = shadow
真实生产  = 未进入
```

---

## 已完成功能

| 模块 | 状态 |
| --- | --- |
| Phase 1-4 核心基础 | 完成（task/result/error model, fetcher, parser engine, CSS/XPath/JSON/jsonld/fallback parser, schema/normalizer/validator/quality_score, storage/dedup/checkpoint/export, observability/logger） |
| Phase 5 AI Provider + Review | 完成（AI client, openai_compatible, dedup store, repair review store, pending_review gate） |
| Phase 6 Shadow 主链路 | 完成（ACS shadow collect, AI parser fallback, audit log, cost report, shadow smoke test） |
| Phase 7 Web Dashboard + 运维 | 完成（Flask Dashboard, 7 页面 + API, 本地鉴权, 告警规则, 日报/周报, 真实 API 调用验证） |
| Phase 8 生产就绪化 | 完成（Chart.js 图表 API, 多站点配置, scheduler cron 导出, health check 15 项, backup, log rotation, data retention, release checklist） |
| Phase 9 On-mode 评估框架 | 完成（readiness scoring, page_type 分类, risk classifier, canary plan, rollback plan, manual approval gate, shadow batch collector） |
| Phase 10 Sandbox Canary | 完成（canary runner, canary monitor, rollback executor, Dashboard evaluation page） |
| ACS UI 业务向导版 | 完成（默认首页, 5 页面, 明暗主题, Toast, 折叠诊断, 无密钥泄露） |

---

## UI 业务向导版

| 项目 | 说明 |
| --- | --- |
| 文件 | `acs_ui/index.html` + `styles.css` + `app.js` |
| 打开方式 | 双击 `index.html`，本地静态打开，不依赖后端 |
| 导航 | 1. 运行总览 / 2. 合规确认 / 3. 模拟测试 / [诊断] ×2 |
| 首页 | 4 用户卡片 + 4 操作按钮 |
| 诊断 | 环境就绪度 + 发布阻塞项（开发者信息折叠） |

---

## Readiness 状态

| 站点 | 样本 | 成功率 | 完整度 | 等级 |
| --- | --: | --: | --: | --- |
| books.toscrape.com | 352 | 100% | 63.5% | **READY** |
| 真实目标站点 | 0 | — | — | **未完成** |

---

## Sandbox Canary

| 项目 | 状态 |
| --- | --- |
| canary runner | dry-run / execute / rollback 全部通过 |
| canary monitor | error_rate / completeness_drop / cost_limit 监控就绪 |
| rollback executor | 11-step shadow 恢复已验证 |
| 真实平台 canary | **未执行** |
| canary_sandbox 模式 | 仅测试站点 |

---

## 测试结果

```
529/529 pytest
 15/15 health_check
 11/11 release_checklist
  8/8 adapter
 14/14 self-test
```

---

## 已知限制

1. **真实目标站点 readiness 未完成** — 需要单一域名 ≥100 条合规 HTML 产品详情页
2. **商业平台存在反爬边界** — Amazon/Walmart/BestBuy/HomeDepot 等返回 403，不可绕过
3. **Chart.js 依赖 CDN** — 离线环境需本地化部署 chart.js
4. **Dashboard 默认 127.0.0.1** — 公网访问需显式配置 `DASHBOARD_TOKEN`
5. **scheduler 为 CLI 手动触发** — 未接入系统 cron/cronjob 自动调度

---

## 不支持事项

| 事项 | 说明 |
| --- | --- |
| 真实生产 on-mode | `ACS_MODE=on` 未启用 |
| 真实商业平台 canary | 未执行，且不可执行 |
| 绕过反爬/登录/验证码 | 禁止 |
| AI Parser 替代旧流程 | 禁止，旧流程仍是唯一正式输出 |
| Self-Healing 自动覆盖 | `auto_apply=False` 硬编码 |

---

## 下一步路线

| 方向 | 条件 |
| --- | --- |
| **A**: 真实目标站点准入 | 提供单一域名 ≥100 条合规 HTML 产品详情页 URL |
| **B**: JSON API readiness | 新增 JSON API 独立准入体系 |
| **C**: 继续 sandbox 增强 | Dashboard 实时监控 / cronjob 自动调度 |
| **Phase 10 真实生产** | 等待合规数据源 + readiness=READY + 人工审批 |
