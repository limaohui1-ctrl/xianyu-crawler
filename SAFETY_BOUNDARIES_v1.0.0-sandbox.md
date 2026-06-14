# SAFETY BOUNDARIES — ACS v1.0.0-sandbox

---

## 版本

**ACS v1.0.0-sandbox（生产前安全冻结版）**

---

## 核心安全原则

当前版本处于 **安全测试模式（shadow）**，以下所有事项均为**永久禁止**。

---

## 禁止事项清单

| # | 禁止事项 | 说明 |
| --- | --- | --- |
| 1 | **不启用 `ACS_MODE=on`** | 始终保持安全测试模式（shadow） |
| 2 | **不对真实商业平台执行 canary** | Amazon/Walmart/BestBuy/HomeDepot 等平台已确认 403 拦截 |
| 3 | **不绕过 403 / 401 / 429** | 反爬拦截、认证要求、限流均不可绕过 |
| 4 | **不绕过登录** | 不对需要账号密码的页面进行采集 |
| 5 | **不绕过验证码** | 不破解、不绕过任何人机验证 |
| 6 | **不绕过付费墙** | 不对付费内容进行采集 |
| 7 | **不绕过访问控制** | 遵守目标站点的 robots.txt 和访问规则 |
| 8 | **不规避反爬机制** | 不使用代理池、伪造 UA、JS 逆向等手段 |
| 9 | **不高频请求** | 每次请求间隔 ≥2 秒 |
| 10 | **不采集未授权内容** | 仅限公开或用户有权访问的页面 |
| 11 | **不输出 API Key** | 日志、报告、页面、异常栈均不得包含 |
| 12 | **不输出 Cookie** | 同上 |
| 13 | **不输出 Token** | 同上 |
| 14 | **不输出 Authorization** | 同上 |
| 15 | **不把测试站点 READY 写成真实 READY** | books.toscrape.com 是测试站点，不代表真实目标站点 |
| 16 | **不把 sandbox 演练写成生产上线** | Sandbox Canary ≠ 真实生产 canary |
| 17 | **不让 AI Parser 替代旧流程** | 旧流程仍是唯一正式输出 |
| 18 | **不让 Self-Healing 自动覆盖规则** | `auto_apply=False` 硬编码 |
| 19 | **不让 approved 候选自动应用** | 必须人工审核 |
| 20 | **不删除历史失败记录美化成功率** | 403/404/timeout 保留在审计日志中 |

---

## 当前安全确认

```
✅ ACS_MODE=shadow
✅ real_phase10=false
✅ real_target_canary=false
✅ acs_mode_on=false
✅ sandbox_only=true
✅ API Key 泄露=0
```

---

## 安全审计

| 检查项 | 方法 | 结果 |
| --- | --- | --- |
| 源码中 API Key | grep "sk-" 等模式 | 0 匹配 |
| 日志中 API Key | 检查 `logs/` `acs_shadow_logs/` | 0 匹配 |
| UI 中 API Key | 检查 `acs_ui/` 全部文件 | 0 匹配 |
| 报告中 API Key | 检查报告 Markdown | 0 匹配 |
| `.env` gitignore | `git check-ignore .env` | 已忽略 |
| `.env.smoke` gitignore | `git check-ignore .env.smoke` | 已忽略 |

---

## 违规处理

如发现违反上述安全边界的行为，应立即停止操作，恢复 `ACS_MODE=shadow`，输出事件记录，并通知相关责任人。
