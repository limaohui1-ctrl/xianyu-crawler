# README — ACS v1.0.0-sandbox 使用说明

---

## 版本

**ACS v1.0.0-sandbox（生产前安全冻结版）**

---

## 打开 UI

双击文件：

```
D:\咸鱼爬取软件\acs_ui\index.html
```

或在终端运行：

```cmd
start D:\咸鱼爬取软件\acs_ui\index.html
```

> 当前 UI 不依赖后端，可直接本地静态打开。

---

## UI 页面说明

| 导航入口 | 页面 | 给谁看 |
| --- | --- | --- |
| 1. 运行总览 | 系统状态 / 可做什么 / 下一步 / 发布状态 | 普通用户 |
| 2. 合规确认 | 合规清单 / 安全边界说明 | 普通用户 |
| 3. 模拟测试 | 小范围模拟测试状态 / 恢复记录 | 普通用户 |
| [诊断] 环境就绪度 | Readiness 评估 / 测试站点 / 真实目标站点 | 开发者 |
| [诊断] 发布阻塞项 | 阻塞项矩阵 / 下一步建议 | 开发者 |

> 普通用户只需查看前 3 个页面；`[诊断]` 页面为开发者保留。

---

## 当前默认模式

```
安全测试模式（ACS_MODE=shadow）
真实生产未启用
```

---

## 功能操作

| 操作 | 方式 |
| --- | --- |
| 导出 JSON 报告 | 点击右上角"▼ 导出报告"按钮 |
| 切换明暗主题 | 左侧导航底部"☾ 暗色 / ☀ 亮色" |
| 查看高级详情 | 点击"展开高级详情"折叠面板 |
| 查看诊断信息 | 点击左侧 `[诊断]` 入口 |

---

## 命令行验证

```bash
cd "D:\咸鱼爬取软件"

# 运行测试
D:/Python312/python.exe -m acs.adapter
D:/Python312/python.exe main.py --self-test
D:/Python312/python.exe -m pytest tests/ -k "not test_live_get"

# 健康检查
D:/Python312/python.exe -m acs.ops.health_check
D:/Python312/python.exe -m acs.ops.release_checklist

# readiness 评估
D:/Python312/python.exe -m acs.evaluation.on_mode_readiness \
  --site-id books_toscrape_real \
  --domain books.toscrape.com \
  --page-type html_product_detail_page
```

---

## 如需进入真实生产

必须满足以下全部条件：

- 提供单一真实域名 ≥100 条合规 HTML 产品详情页 URL
- `attempt_success_rate ≥ 85%`
- `avg_completeness ≥ 60%`
- `readiness_level = READY`
- 人工审批通过
- `ACS_MODE` 保持 `shadow`，不自动切换 `on`

当前上述条件未满足，**真实生产未进入**。
