# 常见问题

## 启动问题

### 软件启动后闪退
1. 检查 `%LOCALAPPDATA%\UniversalWebCollector\startup_error.log`
2. 常见原因：缺少 Python 依赖。运行 `pip install -r requirements.txt`
3. 如打包版闪退，检查杀毒软件是否拦截了 PyInstaller 打包的 EXE

### "找不到 Python" 或 "python 不是内部命令"
- 源码运行需要 Python 3.11+，下载地址：https://www.python.org/downloads/
- 安装时勾选 "Add Python to PATH"

### "No module named 'PyQt6'"
```powershell
pip install PyQt6
```

---

## 采集问题

### 采集结果为空或很少
1. 确认网址可正常访问（浏览器打开测试）
2. 尝试切换到"完整"模式（更多翻页和子页面）
3. 如果网站需要登录，勾选"保留登录状态"并先用"打开登录浏览器"登录
4. 检查"抓取前风险检查"结果，可能有 robots.txt 限制

### 采集报错 "403 Forbidden" 或 "反爬"
1. 启用"使用真实浏览器采集动态网页"
2. 增加"访问间隔"（建议 3-5 秒）
3. 勾选"保留登录状态"并用"打开登录浏览器"完成登录
4. 如果持续失败，该网站可能主动阻止自动化访问

### 采集到了但完整度很低
1. 点击"重抓低完整度"按钮，自动使用完整模式补全
2. 查看"诊断建议"区域的具体原因
3. 如果提示"分页未继续"，点击"重抓分页"
4. 如果提示"子链接未展开"，点击"重抓子链接"

### 采集太慢
1. 降低"采集深度"（选择"普通"模式）
2. 减少"子页面上限"（批量采集标签页中）
3. 减少"翻页上限"
4. 减少"滚动次数"

---

## AI 配置问题

### "请先配置 API Base URL" / "请先填写 API Key"
1. 在一键采集页面展开"AI 设置"区域
2. 选择 API 厂商（如 DeepSeek、OpenAI、通义千问等）
3. 填写 API Key（从对应厂商后台获取）
4. 点击"保存"，然后点击"测试"确认连接正常

### API 测试返回 "401 Unauthorized"
- API Key 错误或已过期，请到对应厂商后台重新生成

### API 测试返回 "Connection refused" 或超时
- 检查网络连接
- 如果使用代理，检查系统代理设置
- 尝试更换厂商（有些厂商在国内访问不稳定）

### "AI 建议列"无反应
- 确保已完成 AI 设置（厂商 + Key + 保存 + 测试通过）
- AI 功能需要模型支持，确认选择的模型在厂商列表中
- 先点击"保存"再点击"AI 建议列"

---

## 打包问题

### PyInstaller 打包后 EXE 启动失败
1. 检查 `通用网站采集中心.spec` 中 `hiddenimports` 是否完整
2. 缺少依赖时在 `requirements.txt` 中添加并重新 `pip install`
3. 杀毒软件可能拦截：尝试添加信任或临时关闭
4. 查看打包目录下的错误日志

### 打包后中文路径乱码
- 确保 `.spec` 文件使用 UTF-8 编码
- 发布包路径避免使用特殊字符

---

## 数据问题

### 采集结果保存在哪里
- 导出文件：当前工作目录的 `采集结果导出\` 下
- 数据库：`%LOCALAPPDATA%\UniversalWebCollector\collector.sqlite3`

### 如何备份配置和数据
1. 复制 `%LOCALAPPDATA%\UniversalWebCollector` 整个目录
2. 包含：AI 设置、站点模板、采集数据库、计划任务、变更提醒

### 如何清除所有数据重新开始
1. 关闭软件
2. 删除 `%LOCALAPPDATA%\UniversalWebCollector` 目录
3. 重新启动软件，将使用默认配置

### 软件卡住了
1. 点击"停止"按钮中断当前采集
2. 如果无响应，通过任务管理器结束进程
3. 重启软件后数据不会丢失（采集结果已实时保存到数据库）

---

## Playwright 浏览器问题

### "playwright 未安装" 或 chromium 下载失败
```powershell
pip install playwright
python -m playwright install chromium
```
如果下载慢，设置镜像：
```powershell
$env:PLAYWRIGHT_DOWNLOAD_HOST="https://npmmirror.com/mirrors/playwright/"
python -m playwright install chromium
```

### "浏览器启动失败"
- 检查 C 盘剩余空间（Playwright chromium 需要约 300MB）
- 系统缺少 Visual C++ 运行时：下载安装 [VC_redist.x64.exe](https://aka.ms/vs/17/release/vc_redist.x64.exe)

---

*最后更新：2026-06-13*
