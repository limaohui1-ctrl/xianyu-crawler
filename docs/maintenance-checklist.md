# 维护与自测清单

## 每次发布前必跑

```powershell
$files = @('main.py','universal_core.py','core_export.py','core_database.py','core_ai_storage.py','universal_ui.py','universal_self_test.py','universal_self_test_runtime.py','ui_ai_settings.py','ui_history.py','ui_exports.py','ui_queue.py','ui_ai_history.py','ui_export_utils.py') + (Get-ChildItem -LiteralPath 'legacy_xianyu' -Filter '*.py' | ForEach-Object { $_.FullName })
python -m py_compile @files
python main.py --self-test
python main.py --self-test --xianyu
python -m PyInstaller --noconfirm '通用网站采集中心.spec'
& 'D:\咸鱼爬取软件\dist\通用网站采集中心\通用网站采集中心.exe' --self-test
powershell -NoProfile -ExecutionPolicy Bypass -File .\build_release.ps1
```

## 当前自测覆盖点

- 通用采集首页、采集流程、状态表、结果质量检查
- AI 建议列、AI 修复字段、AI 调用日志、AI 用量汇总
- API Key 加密落盘，不允许明文保存在 `ai_settings.json`
- CSV/XLSX 公式注入转义
- AI 修复历史导出、复用和局部应用
- 任务队列、任务档案、计划采集、变更提醒
- 文件转表格、AI 表格导出、图片下载
- 用户数据清理：删除 Key/历史/日志/登录态，保留模板库
- 旧版入口已归档，不再维护

## 下一轮拆分建议

1. 已完成：通用自测拆到 `universal_self_test.py`，`universal_ui.py` 保留兼容包装入口。
2. 已完成：AI 配置页构建拆到 `ui_ai_settings.py`，事件处理仍保留在 `UniversalMainWindow` 里作为稳定过渡。
3. 已完成：历史与监控页构建拆到 `ui_history.py`，导出/复制动作拆到 `ui_exports.py`，任务队列/失败恢复动作拆到 `ui_queue.py`，AI 调用日志/修复历史动作拆到 `ui_ai_history.py`，导出后缀补全拆到 `ui_export_utils.py`；部分刷新/筛选事件处理仍保留在 `UniversalMainWindow` 里作为稳定过渡。
4. 已完成：采集记录、表格、TSV 导出实现拆到 `core_export.py`，`universal_core.py` 通过重导出保持原接口。
5. 已完成：SQLite 数据库、任务运行档案和变更报告查询拆到 `core_database.py`，默认运行时路径通过 `universal_core.CollectorDatabase` 包装保持不变。
6. 已完成：AI Key 本机加密、AI 调用日志和修复历史 JSONL 存储拆到 `core_ai_storage.py`，默认运行时路径仍通过 `universal_core` 包装。
7. 已完成：自测运行时隔离和旧文件清理拆到 `universal_self_test_runtime.py`，便于后续继续按断言场景拆分。
4. 下一步可拆出导出逻辑或把 AI/历史事件处理逐步搬到对应模块。
5. 保持 `main.py`、启动脚本和 PyInstaller spec 不变，避免普通用户入口漂移。
6. 拆分后每一步都先跑源码自测，再跑打包版自测。
