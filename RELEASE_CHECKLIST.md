# 发布前检查清单

每次发布前请按以下清单逐项检查。所有项目通过后才可发布。

---

## 一、代码检查

- [ ] `python tools/verify_repo_hygiene.py` 通过
- [ ] `.gitignore` 覆盖所有运行数据、采集结果、打包目录和浏览器登录态
- [ ] 无敏感文件（`.env`、真实 `ai_settings.json`、日志文件）被 Git 跟踪
- [ ] 所有 Python 文件编译通过：`for f in *.py ui_*.py core_*.py tools/*.py legacy_xianyu/*.py; do python -m py_compile "$f"; done`
- [ ] 无遗留的调试代码、print 语句、硬编码路径

## 二、测试

- [ ] `python main.py --self-test` 全部通过（14/14）
- [ ] `python main.py --self-test --xianyu` 通过（如有旧版兼容需求）
- [ ] 手动验证以下核心操作路径：
  - [ ] 首次启动 → 看到一键采集界面
  - [ ] 输入网址 → 选择深度 → 确认并采集 → 查看结果 → 导出
  - [ ] 专家模式切换 → AI 工作台 / 批量采集 / 模板库 / 历史与监控 均可访问
  - [ ] AI 设置 → 选择厂商 → 填 Key → 保存 → 测试 API
  - [ ] 定时采集 → 创建 → 查看计划列表 → 启用/停用 → 删除
  - [ ] 变更提醒 → 查看 → 标记已处理 → 筛选

## 三、打包

- [ ] `pip install -r requirements.txt` 在新 venv 中可完成安装
- [ ] `python -m playwright install chromium` 可安装浏览器
- [ ] `python -m PyInstaller --noconfirm '通用网站采集中心.spec'` 构建成功
- [ ] 打包后的 EXE 在干净 Windows 环境（无 Python 安装）可启动
- [ ] 打包后的 EXE 在中文路径下可启动（如 `D:\通用网站采集中心_发布包\`）
- [ ] 发布包不包含 `.git` 目录、`__pycache__`、自测数据、浏览器登录态
- [ ] 桌面快捷方式创建成功

## 四、文档

- [ ] `README.md` 内容与当前版本一致
- [ ] `CHANGELOG.md` 已更新，列出本次发布的所有变更
- [ ] `RELEASE_CHECKLIST.md` 本文件所有项已勾选
- [ ] `SECURITY.md` 安全联系人信息有效
- [ ] `TROUBLESHOOTING.md` 常见问题覆盖当前已知问题

## 五、版本与发布

- [ ] `APP_VERSION` 已更新（`universal_core.py`）
- [ ] Git 提交所有变更，commit message 清晰
- [ ] Git tag 已打（如 `v2026.06.13-ai-agent115`）
- [ ] 发布包文件已放置到目标目录
- [ ] 已通知相关人员发布完成

## 六、回滚方案

如发布后出现严重问题：

1. `git checkout <上一个稳定版本的 tag>`
2. 重新打包并替换发布目录
3. 通知用户回滚
4. 在 CHANGELOG 中标注回滚版本

---

*最后更新：2026-06-13*
