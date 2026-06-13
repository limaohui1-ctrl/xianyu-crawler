# 配置指南

## 数据位置

| 内容 | 路径 |
|------|------|
| 采集数据库 | `%LOCALAPPDATA%\UniversalWebCollector\collector.sqlite3` |
| AI 设置（加密） | `%LOCALAPPDATA%\UniversalWebCollector\ai_settings.json` |
| 站点模板 | `%LOCALAPPDATA%\UniversalWebCollector\site_templates.json` |
| 计划采集 | `%LOCALAPPDATA%\UniversalWebCollector\schedules.json` |
| 计划采集备份 | `%LOCALAPPDATA%\UniversalWebCollector\schedules.json.bak` |
| AI 调用日志 | `%LOCALAPPDATA%\UniversalWebCollector\ai_call_logs.jsonl` |
| AI 修复历史 | `%LOCALAPPDATA%\UniversalWebCollector\ai_repair_history.jsonl` |
| 风险确认记录 | `%LOCALAPPDATA%\UniversalWebCollector\risk_confirmations.json` |
| 变更提醒状态 | `%LOCALAPPDATA%\UniversalWebCollector\change_alert_states.json` |
| 启动错误日志 | `%LOCALAPPDATA%\UniversalWebCollector\startup_error.log` |
| 导出文件 | 当前目录的 `采集结果导出\` |

## AI 配置

### 支持的厂商

软件内置 18 个 AI 厂商预设：

| 厂商 | 配置说明 |
|------|---------|
| OpenAI | 需 API Key（从 platform.openai.com 获取） |
| DeepSeek | 需 API Key（从 platform.deepseek.com 获取） |
| Anthropic Claude | 需 API Key（从 console.anthropic.com 获取） |
| Google Gemini | 需 API Key（从 aistudio.google.com 获取） |
| 通义千问 (Qwen) | 需 API Key（从 dashscope.aliyun.com 获取） |
| 混元 (Hunyuan) | 需 API Key（从 hunyuan.tencentcloud.com 获取） |
| 豆包 (Doubao) | 需 API Key（火山引擎控制台） |
| Kimi / Moonshot | 需 API Key（从 platform.moonshot.cn 获取） |
| 智谱 (Zhipu) | 需 API Key（从 open.bigmodel.cn 获取） |
| xAI / Grok | 需 API Key |
| Mistral | 需 API Key（从 console.mistral.ai 获取） |
| Groq | 需 API Key（从 console.groq.com 获取） |
| Together | 需 API Key |
| Perplexity | 需 API Key |
| OpenRouter | 需 API Key（从 openrouter.ai 获取） |
| SiliconFlow | 需 API Key（从 siliconflow.cn 获取） |
| Thunderbit 抽取 | 第三方网页抽取接口（非通用大模型） |
| 自定义 | 填写任意 OpenAI 兼容 API 的 Base URL |

### 配置步骤

1. **一键采集页面** → 展开右侧"AI 设置" → 选择厂商 → 填写 Key → 点"保存" → 点"测试"
2. **专家模式** → "AI 抓取工作台" → 可切换多组 API Key、选择模型、配置网络搜索

### API Key 安全

- Key 输入框使用密码模式（输入时显示为 ●●●●）
- 保存后使用 Windows DPAPI 加密存盘
- 日志输出中自动脱敏（显示为 `sk-...xxxx`）
- 任务档案不保存明文 Key

### 配置恢复

如配置损坏导致软件异常：
1. 关闭软件
2. 删除 `%LOCALAPPDATA%\UniversalWebCollector\ai_settings.json`
3. 重新启动，将恢复默认 AI 设置

---

## 采集深度说明

| 模式 | 翻页 | 子页面 | 滚动 | 适用场景 |
|------|------|--------|------|---------|
| 普通 | 1 页 | 最多 3 个 | 1 次 | 简单网页，快速预览 |
| 深度 | 3 页 | 最多 12 个 | 3 次 | 常规采集，推荐默认 |
| 完整 | 5 页 | 最多 30 个 | 5 次 | 需要尽可能完整的数据 |

可在批量采集页面精细调整：翻页上限、子页面上限、滚动次数、访问间隔。

---

## 定时采集

1. 输入网址 → 选择深度 → 点击"定时监控"
2. 输入间隔分钟数（建议 30 分钟以上）
3. 确认风险摘要后创建
4. 在"历史与监控" → "计划采集"中管理（启用/停用/删除/立即运行）

**注意**：定时采集需软件保持运行。关闭软件后定时任务不会执行。

---

## 浏览器登录

部分网站需要登录才能看到完整内容：

1. 在"批量采集"页面勾选"保留登录状态"
2. 点击"打开登录浏览器"
3. 在浏览器中完成登录（输入账号密码、过验证码等）
4. 关闭浏览器
5. 后续采集将复用登录状态

---

## 模板管理

软件内置 20+ 个行业模板（电商、房产、招聘、企业黄页、本地服务等）。
可在"模板库"中搜索、安装、编辑模板。

### 场景模板预设
点击"一键套用场景"可快速切换模板套件，包括：
- 电商商品页、列表页、详情页
- 房产房源页
- 招聘职位页
- 企业黄页
- 新闻文章页
- 等等

---

## 备份与迁移

### 备份
复制整个 `%LOCALAPPDATA%\UniversalWebCollector` 目录：
```powershell
Copy-Item -Recurse "$env:LOCALAPPDATA\UniversalWebCollector" "D:\备份\UniversalWebCollector_$(Get-Date -Format 'yyyyMMdd')"
```

### 迁移到新电脑
1. 复制备份目录到新电脑
2. 放置到 `%LOCALAPPDATA%\UniversalWebCollector`
3. **注意**：API Key 使用 DPAPI 加密，绑定原系统用户。迁移后需重新配置 AI Key

### 重置
```powershell
# 关闭软件后执行
Remove-Item -Recurse "$env:LOCALAPPDATA\UniversalWebCollector"
```

---

*最后更新：2026-06-13*
