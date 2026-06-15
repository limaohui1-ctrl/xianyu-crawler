# ACS 资料采集助手 — 首次使用说明

> 输入主题，全网找资料，采集正文，整理导出。

适用用户：普通 Windows 用户。

---

## 安装前准备

1. **安装 Docker Desktop**（必需）
   - 下载：https://www.docker.com/products/docker-desktop/
   - 安装后启动 Docker Desktop，等待右下角 Docker 图标变绿。

2. **确认 Python 已安装**
   ```powershell
   python --version   # 需要 Python 3.11+
   ```

---

## 第一步：部署本地 SearXNG 搜索引擎

详参考 `docs/SEARXNG_SETUP.md`，简要步骤：

```powershell
# 创建部署目录
mkdir D:\ACS_SearXNG
cd D:\ACS_SearXNG
mkdir searxng

# 将 docker-compose.yml 和 settings.yml 放入该目录（见 SEARXNG_SETUP.md）

# 启动
docker compose up -d

# 验证
curl.exe "http://127.0.0.1:8080/search?q=园区废气治理案例&format=json"
```

---

## 第二步：配置 ACS 资料采集助手

```powershell
# 复制配置模板
copy .env.example .env

# 默认配置已可用（ACS_MODE=shadow, SearXNG 本机地址）
```

---

## 第三步：启动 ACS

**推荐：双击 `启动ACS资料采集助手.bat`**

或命令行：
```powershell
python start_acs_desktop.py
```

启动后应看到：

```
[OK] 本地 SearXNG 已连接
```

---

## 第四步：输入主题找资料

1. 在「主题搜索」输入框中输入主题，例如：`园区废气治理案例`
2. 可选输入关键词（逗号分隔）：`VOCs, 活性炭, 整改报告`
3. 点击「搜索」
4. 系统会从全网返回候选资料

---

## 第五步：选择候选资料

1. 在候选列表中选择允许采集的资料（勾选 allowed）
2. 系统自动标记需要复核的资料
3. 点击「确认选择」

---

## 第六步：导出资料

确认采集完成后，可导出以下格式：

| 格式 | 说明 |
|------|------|
| **Excel (.xlsx)** | 带颜色标记，推荐 |
| **CSV** | UTF-8 编码，可导入其他工具 |
| **JSON** | 完整结构化数据 |
| **Markdown** | 可读文本，适合存档或分享 |

---

## 常见错误

| 错误 | 处理方法 |
|------|----------|
| Docker 未启动 | 打开 Docker Desktop，等待图标变绿 |
| 8080 端口被占用 | 结束占用进程，或修改 SearXNG 端口 |
| SearXNG 返回空结果 | 换一个更短/更通用的关键词重试 |
| ACS 无法连接 SearXNG | 检查 `.env` 中 `ACS_SEARXNG_BASE_URL` |
| 中文乱码 | 用 Excel 打开 CSV 时选择 UTF-8 编码 |
| 双击 .bat 无反应 | 用 PowerShell 运行 `python start_acs_desktop.py` 查看错误 |

---

## 安全说明

- 当前版本默认运行在 **shadow 模式**（安全测试模式）
- **不会执行真实生产采集**
- **不会发送数据到外部服务器**
- `.env` 中的配置仅保存在本机

---

## 更多帮助

- SearXNG 详细部署：`docs/SEARXNG_SETUP.md`
- 故障排查：`docs/TROUBLESHOOTING.md`
- 完整文档：`README.md`
