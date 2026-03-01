# 2026-03-01 发布交付说明（Release Handoff）

Owner: Maintainer  
Date: 2026-03-01

---

## 1. 发布门禁状态快照

- Gate 1（`P1/P2` 缺陷）：通过。
- Gate 2（桌面 + 移动端核心流程）：待人工真机验收。
- Gate 3（WebDAV 关键链路）：待人工端到端验收。
- Gate 4（自动化回归命令）：通过（`node --check` + 17 项 `unittest`）。

结论：
- 在 Gate 2 / Gate 3 未完成勾选前，不可发布。

---

## 2. 人工验收执行入口

1. 启动验收环境：

```bash
scripts/qa/manual_acceptance_bootstrap.sh --config config.toml --host 127.0.0.1 --port 18000
```

2. 一键生成本轮验收包（Gate 2 + Gate 3 报告 + 总览）：

```bash
scripts/qa/new_acceptance_packet.sh
```

3. 完成人工验收并回填：
- `artifacts/manual-qa/<timestamp>/gate2-report.md`
- `artifacts/manual-qa/<timestamp>/gate3-report.md`
- `docs/plans/2026-03-01-release-acceptance-checklist.md`

4. 生成门禁状态快照（可选严格模式）：

```bash
scripts/qa/check_acceptance_status.sh --strict
```

5. 停止验收环境：

```bash
scripts/qa/manual_acceptance_stop.sh
```

---

## 3. 发布说明草稿（可直接用于 GitHub Release）

建议标题：
- `UI/Mobile/WebDAV polish release`

建议摘要：
- 首页批量工具栏、状态反馈与禁用原因提示增强，降低误操作成本。
- 移动端交互完成一轮重点优化：顶部布局、批量工具栏换行、对话框粘附操作栏、底部导航锚点高亮与滚动体验。
- 可访问性基线增强：`aria-live`、`aria-current`、`aria-expanded`、对话框焦点回退、`prefers-reduced-motion` 兼容。
- WebDAV 诊断与缓存异常链路增强：异常仓库 Top 展示、缓存异常筛选/选中守卫、批量动作前置条件明确。
- 验收执行工具链补全：`manual_acceptance_bootstrap.sh`、`manual_acceptance_stop.sh`、`new_gate2_report.sh`、`new_gate3_report.sh`、`new_acceptance_packet.sh`。

---

## 4. 已知限制与风险提示

- Gate 2 / Gate 3 仍依赖真实设备与真实 WebDAV 环境人工验收。
- 本机 Python 运行时存在 `urllib3 NotOpenSSLWarning`（LibreSSL），当前不阻塞功能回归，但建议在发布环境统一 OpenSSL 版本。

---

## 5. 打标与发布步骤（门禁通过后执行）

1. 确认门禁清单全部通过并提交：
- `docs/plans/2026-03-01-release-acceptance-checklist.md`
- `artifacts/manual-qa/<timestamp>/gate2-report.md`
- `artifacts/manual-qa/<timestamp>/gate3-report.md`

2. 创建版本标签（示例）：

```bash
git checkout main
git pull --ff-only
git tag -a vX.Y.Z -m "Release vX.Y.Z"
git push origin main
git push origin vX.Y.Z
```

3. 在 GitHub Release 页面粘贴第 3 节摘要，并附 Gate 2 / Gate 3 证据链接。

---

## 6. 回滚说明（若发布后触发阻塞问题）

1. 使用上一个稳定标签执行回滚（代码层）。
2. 保留 `config.override.json`、`state.json` 与下载目录数据，不做删除。
3. 回滚后执行最小冒烟：
- 登录
- 首页加载
- 单仓库检查
- 批量检查
- 设置页测试 WebDAV
