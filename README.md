# 通用网站采集中心

面向普通用户的 Windows 桌面采集工具，支持通用网页采集、AI 字段建议、文件转表格、历史记录、变更提醒，以及旧版闲鱼监测兼容入口。

## 启动

- 源码运行：双击 `启动通用网站采集中心.bat`，或执行 `python main.py`
- 旧版闲鱼兼容入口：执行 `python main.py --xianyu`
- 发布包入口：`D:\通用网站采集中心_发布包\通用网站采集中心\通用网站采集中心.exe`

## 数据位置

- 通用采集运行数据默认保存在 `%LOCALAPPDATA%\UniversalWebCollector`
- 旧版闲鱼兼容数据默认保存在 `%LOCALAPPDATA%\XianyuMonitor`
- API Key 使用 Windows DPAPI 按当前系统用户加密保存，配置文件中不应出现明文 Key
- 发布包不包含历史采集库、浏览器登录态、诊断日志或自测数据

## 验证

```powershell
$files = @('main.py','universal_core.py','core_urls.py','core_export.py','core_database.py','core_ai_storage.py','core_firecrawl.py','core_firecrawl_flow.py','universal_ui.py','ui_firecrawl.py','ui_workers.py','universal_self_test.py','universal_self_test_runtime.py','ui_ai_settings.py','ui_history.py','ui_exports.py','ui_queue.py','ui_ai_history.py','ui_export_utils.py','tools/verify_repo_hygiene.py') + (Get-ChildItem -LiteralPath 'legacy_xianyu' -Filter '*.py' | ForEach-Object { $_.FullName })
python -m py_compile @files
python tools/verify_repo_hygiene.py
python main.py --self-test
python main.py --self-test --xianyu
```

## 打包

```powershell
python -m PyInstaller --noconfirm '通用网站采集中心.spec'
powershell -NoProfile -ExecutionPolicy Bypass -File .\build_release.ps1
```

发布目录会生成到 `D:\通用网站采集中心_发布包\通用网站采集中心`，并更新桌面快捷方式。

## 维护重点

- 通用自测已拆到 `universal_self_test.py`，AI 配置页构建已拆到 `ui_ai_settings.py`，历史与监控页构建已拆到 `ui_history.py`，导出/复制动作已拆到 `ui_exports.py`，任务队列/失败恢复动作已拆到 `ui_queue.py`，AI 调用日志/修复历史动作已拆到 `ui_ai_history.py`，导出路径补后缀逻辑已统一到 `ui_export_utils.py`；`universal_ui.py` 后续仍可继续拆出事件处理。
- 核心导出实现已拆到 `core_export.py`，`universal_core.py` 仍重导出原有函数名，外部调用方式保持不变。
- SQLite 数据库、运行档案和变更报告查询已拆到 `core_database.py`，`universal_core.py` 用兼容包装类保留原默认数据目录。
- AI Key 本机加密、AI 调用日志和修复历史 JSONL 存储已拆到 `core_ai_storage.py`，`universal_core.py` 仍保留原函数名和运行时路径默认值。
- Firecrawl 远程/自托管增强采集适配已拆到 `core_firecrawl.py`，采集编排在 `core_firecrawl_flow.py`，UI 配置在 `ui_firecrawl.py`；当前接入 `scrape`、`map`、`search`、`extract`、`batch scrape`、`crawl`、`parse` 与 `interact`；任务档案只保存 Key 摘要，不保存明文 Key。
- 自测运行时目录隔离和旧文件清理已拆到 `universal_self_test_runtime.py`，主自测文件更聚焦断言流程。
- 每次改动导出、AI Key、采集流程或打包脚本后，都需要跑完整自测。
- 准备同步 GitHub 前，先执行 `python tools/verify_repo_hygiene.py`，确认 `.gitignore` 覆盖运行数据、采集结果、打包目录和浏览器登录态，且这些产物未被 git 跟踪。
