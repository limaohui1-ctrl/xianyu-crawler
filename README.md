# ACS 资料采集助手

**输入主题，自动全网找资料，采集正文，整理导出。**

> v1.3.1-delivery-cleanup | ACS_MODE=shadow（安全测试模式）

---

## 软件定位

ACS 资料采集助手是一个桌面端资料采集工具。用户输入一个主题或关键词，系统可以：

1. 通过本地自托管 SearXNG 搜索引擎，在全网发现候选资料
2. 确认候选资料后，抓取网页正文并提取标题、作者、发布时间
3. 自动识别资料类型（网页 / PDF / Word / Excel / CSV）
4. 对采集结果进行质量评分和内容去重
5. 将结果导出为 **Excel / CSV / Markdown / JSON**

## 三步使用流程

```
① 输入主题 / 关键词
→ SearXNG 全网搜索候选资料
② 确认候选资料
→ 选择要采集的 URL
③ 采集正文并导出
→ 正文提取 → 质量评分 → 去重 → Excel/CSV/MD/JSON 导出
```

---

## 环境要求

- **Windows 10/11**（x64）
- **Docker Desktop**（运行 SearXNG 搜索引擎）
- **Python 3.11+**（推荐 Python 3.12）
- 安装 Python 依赖：`pip install -r requirements.txt`

---

## 快速开始

### 1. 部署 SearXNG

```bash
# 进入 SearXNG 部署目录
cd D:\ACS_SearXNG

# 启动
docker compose up -d

# 验证
curl http://127.0.0.1:8080/search?q=园区废气治理案例&format=json
```

### 2. 配置 ACS

```bash
# 复制配置模板
cp .env.example .env

# .env 默认配置已可用（ACS_MODE=shadow, SearXNG 本地地址）
```

### 3. 启动 ACS

**推荐方式**：双击 `启动ACS资料采集助手.bat`

**命令行启动**：
```bash
python start_acs_desktop.py           # Web 模式 (127.0.0.1:5020)
python main.py                        # PyQt GUI 桌面应用
```

---

## 当前版本功能

| 功能 | 状态 | 说明 |
|------|------|------|
| SearXNG 全网搜索 | ✅ | 84 个搜索引擎，JSON 格式返回 |
| 网页正文提取 | ✅ | 去除导航、广告，保留正文段落 |
| 资料类型识别 | ✅ | 识别 webpage / pdf / doc / xls / csv |
| 质量评分 | ✅ | 7 维度评分：标题、正文、关键词、登录页检测等 |
| 内容去重 | ✅ | URL / 标题 / 正文相似度 / 域名过多 |
| Excel 导出 | ✅ | 带样式、颜色标记、筛选器 |
| CSV / Markdown / JSON 导出 | ✅ | UTF-8 编码 |
| PDF 正文解析 | ⚠️ | 已识别 PDF，全文解析待增强 |
| 安全模式 | ✅ | ACS_MODE=shadow，不执行真实生产操作 |

---

## 默认安全设置

- **ACS_MODE=shadow**：所有操作在测试模式下运行
- **ACS_MODE=on**：未启用（生产采集模式）
- **真实生产采集**：未启用
- **.env 配置**：已加入 .gitignore，不会提交到 Git
- **API Key 泄露**：已通过自动化检查，源码中无硬编码密钥

---

## 配置说明

复制 `.env.example` 为 `.env`，根据环境修改：

```env
ACS_MODE=shadow
ACS_SEARCH_PROVIDER=searxng
ACS_SEARXNG_BASE_URL=http://127.0.0.1:8080
ACS_SEARXNG_TIMEOUT=15
ACS_SEARXNG_LANGUAGE=zh-CN
```

---

## 导出格式

所有导出文件保存在 `acs_data/harvest/` 目录：

| 格式 | 说明 |
|------|------|
| Excel (.xlsx) | 带样式、颜色标记、筛选器 |
| CSV | UTF-8 BOM 编码 |
| Markdown | 统计摘要 + 独立章节 |
| JSON | 完整结构化数据 |

---

## 如何停止程序

- GUI 模式：关闭窗口，或点击"停止采集"按钮
- Web 模式：按 `Ctrl+C` 终止
- 急停：任务管理器结束 `python.exe` 进程

---

## 已废弃功能

以下功能已从当前版本移除或归档：

- ⛔ 旧版咸鱼爬虫（已归档到 `D:\ACS_Archive\legacy_xianyu_backup\`）
- ⛔ Firecrawl 网页采集（已被 SearXNG + HTTP 正文提取替代）
- ⛔ 旧版"通用网站采集中心"入口（新入口：`启动ACS资料采集助手.bat`）

---

## 测试

```bash
# 全量测试（排除需要网络的真实验证）
python -m pytest tests/ -k "not test_live_get"

# 健康检查
python -m acs.ops.health_check

# 发布检查
python -m acs.ops.release_checklist
```

---

## 日志位置

| 日志 | 路径 |
|------|------|
| Shadow 采集日志 | `acs_shadow_logs/` |
| AI 调用审计 | `logs/ai_call_audit.jsonl` |
| 启动错误日志 | `startup_error.log` |

---

## 常见问题

**Q: 启动后提示"端口已被占用"？**
A: 关闭已运行的 ACS 或占用 5020 端口的程序。

**Q: SearXNG 搜索无结果？**
A: 确认 Docker Desktop 运行中，`docker ps` 查看 `acs-searxng` 容器状态。

**Q: PDF 文件不能提取正文？**
A: 当前版本 PDF 仅识别类型，正文提取将在后续版本实现。

**Q: 旧版咸鱼爬虫还能用吗？**
A: 旧版已归档，当前主线是 ACS 资料采集助手。如需历史版本，请查看 Git 历史或归档目录。

---

## 项目信息

- **版本**：v1.3.1-delivery-cleanup
- **语言**：Python 3.11+ / HTML / JavaScript
- **许可证**：见 LICENSE 文件
- **旧版咸鱼爬虫归档位置**：`D:\ACS_Archive\legacy_xianyu_backup\`
