# ACS 资料采集助手 — 故障排查

## 启动问题

### Docker Desktop 未启动

```
[WARN] 未检测到本地 SearXNG，请先启动 Docker Desktop 和 acs-searxng 容器。
```

**解决：** 打开 Docker Desktop，等待右下角鲸鱼图标变绿，然后运行 `docker compose up -d`。

### 8080 端口被占用

```
[ERROR] SearXNG 启动失败：端口 8080 已被占用。
```

**解决：** 
1. 查看占用进程：`netstat -ano | findstr :8080`
2. 修改 `docker-compose.yml` 中 `ports` 为其他端口，如 `"127.0.0.1:8081:8080"`
3. 同步修改 `.env` 中 `ACS_SEARXNG_BASE_URL=http://127.0.0.1:8081`

### 双击 .bat 无反应

**解决：** 用 PowerShell 运行查看错误详情：
```powershell
cd D:\ACS_PackageSmoke\ACS资料采集助手
python start_acs_desktop.py
```

---

## SearXNG 问题

### 搜索返回空结果

**可能原因：**
1. 搜索引擎超时 — 等几分钟后重试
2. 搜索关键词过于具体 — 尝试更通用的关键词
3. Docker 网络问题 — 重启 Docker Desktop

### SearXNG 返回 403

**解决：** 确认 `settings.yml` 中 `formats` 包含 `json`：
```yaml
search:
  formats:
    - html
    - json    # 必须有这一行
```

### 搜索速度很慢

正常现象 — SearXNG 需要等待多个搜索引擎返回结果，每次查询约 1-5 秒。

---

## ACS 问题

### ACS 无法连接 SearXNG

```
[WARN] 未检测到本地 SearXNG，请先启动 Docker Desktop 和 acs-searxng 容器。
```

**解决：**
1. 确认 `.env` 中 `ACS_SEARXNG_BASE_URL` 地址正确
2. 使用 `curl.exe "http://127.0.0.1:8080/search?q=test&format=json"` 测试连接
3. 如果 SearXNG 部署在其他机器，修改地址为实际 IP

### 采集结果为空

**可能原因：**
1. 目标网站要求登录
2. 目标网站有反爬机制
3. 网络连接问题

**解决：** 检查「失败原因」列，会标注具体错误（HTTP 403 / 超时 / 正文为空 等）

### 导出 Excel 失败

**解决：**
```powershell
pip install openpyxl
```

### 中文乱码

- **CSV 乱码：** 用 Excel 打开时选择「数据 → 从文本/CSV」→ 编码选择「UTF-8」
- **Markdown 乱码：** 用支持 UTF-8 的编辑器打开（VS Code / Notepad++）

---

## 配置问题

### .env 文件不存在

```
未发现 .env 配置文件。
请复制 .env.example 为 .env。
```

**解决：**
```powershell
copy .env.example .env
```

### .env.example 也不存在

```
缺少 .env.example，发布包可能不完整。
```

**解决：** 重新下载完整发布包。

---

## 性能问题

### 内存不足

SearXNG 容器建议至少分配 2GB 内存。如果系统内存紧张：
1. 在 Docker Desktop 设置中降低内存限制
2. 关闭不需要的后台应用

### 采集速度慢

正常现象 — 每个网页采集约需要 0.1-2 秒，取决于目标网站响应速度。

---

## 更多帮助

- 首次使用说明：`docs/USER_QUICK_START.md`
- SearXNG 部署说明：`docs/SEARXNG_SETUP.md`
- 完整文档：`README.md`
