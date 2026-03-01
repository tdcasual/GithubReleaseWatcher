# Release Acceptance Checklist (UI/Mobile/WebDAV)

Last update: 2026-03-01  
Owner: Maintainer

---

## 1. Quality Gates

- [x] Gate 1: No open `P1/P2` defects.
- [ ] Gate 2: Core user flows pass on desktop and mobile.
- [ ] Gate 3: WebDAV critical flow passes end-to-end.
- [x] Gate 4: Required automated regression commands pass.

Gate notes:
- Gate 1: 截至 2026-03-01 12:11 CST，当前清单无登记中的 `P1/P2` 缺陷。
- Gate 2: 待完成桌面/移动端真机手工勾选后再置为通过（执行套件：`docs/plans/2026-03-01-gate2-device-acceptance-kit.md`）。
- Gate 3: 待按关键链路进行一次完整人工验收（执行套件：`docs/plans/2026-03-01-gate3-webdav-critical-flow-runbook.md`）。
- Gate 4: `node --check` + 17 项 `unittest` 回归命令集已多次通过，见第 7 节证据。

---

## 2. Defect Severity Rules

- `P1`: Data loss, security risk, or complete flow blocked.
- `P2`: Major feature unusable or strong user confusion on core path.
- `P3`: Non-blocking UX issue with workaround.
- `P4`: Cosmetic/low-impact polish item.

Release rule:
- Any open `P1/P2` => release blocked.

---

## 3. Desktop Manual Checklist

Environment:
- OS: ________
- Browser + version: ________
- Screen size(s): ________

Checks:
- [ ] Login flow works and security banner behavior is correct.
- [ ] Status card numbers/time text update correctly after operations.
- [ ] Repo search + state filter + sort combinations behave consistently.
- [ ] Batch actions (`select/invert/enabled/error/cache-anomaly/run/enable/disable/clear`) match visible data.
- [ ] Disabled buttons include clear reason where applicable.
- [ ] Settings dialog actions (`test/capabilities/sync-cache/cleanup-preview/save`) produce clear feedback.
- [ ] Logs section remains readable and copy action works.

Notes:
- 已完成样式层修复：移动端 topbar 改网格、筛选控件改单列全宽、超窄屏批量工具栏改单列、repo 行控件纵向拉伸。
- 待办：在 iOS Safari / Android Chrome 真机逐项勾选。
- 执行脚本与模板：`docs/plans/2026-03-01-gate2-device-acceptance-kit.md`、`docs/plans/2026-03-01-gate2-device-acceptance-template.md`。

---

## 4. Mobile Manual Checklist

Environment:
- Device 1: ________
- Browser/version: ________
- Device 2: ________
- Browser/version: ________

Checks:
- [ ] Topbar and status card remain readable without overlap.
- [ ] Batch toolbar buttons are tappable and wrap correctly.
- [ ] Repo card controls do not clip or overlap.
- [ ] Dialog actions are reachable and readable at small widths.
- [ ] Scroll behavior is stable when dialogs open/close.
- [ ] Touch target sizes are acceptable for main actions.

Notes:
- 已在响应式模拟下验证布局修复：topbar 网格、筛选控件单列全宽、批量工具栏窄屏降为单列、repo 行控件纵向拉伸。
- 已补充移动端交互优化：底部导航高亮当前区块 + 平滑锚点滚动；批量工具栏与 repo 行控件触控区域加大。
- 已优化长表单对话框：移动端对话框内容可滚动，操作按钮区底部粘附，减少来回滚动成本。
- 待办：在 iOS Safari / Android Chrome 真机完成触控可用性勾选。
- 执行脚本与模板：`docs/plans/2026-03-01-gate2-device-acceptance-kit.md`、`docs/plans/2026-03-01-gate2-device-acceptance-template.md`。

---

## 5. Accessibility Baseline Checklist

- [ ] Keyboard-only navigation reaches all major controls.
- [ ] Focus indicators are visible on actionable controls.
- [ ] Dialog focus behavior and close behavior are consistent.
- [ ] Error/warn text remains readable in light/dark modes.
- [ ] Critical controls have clear labels/aria semantics.

Notes:
- 已完成基础可访问性增强：动态提示区域增加 `aria-live="polite"` 与 `role="status"`。
- 已实现对话框焦点回退：设置/新增仓库对话框关闭后回到触发控件（含关闭后回退到触发按钮兜底）。
- 已补充仓库行交互控件 `aria-label`、折叠按钮 `aria-expanded/aria-controls` 语义、移动导航 `:focus-visible` 样式。
- 已补充移动导航 `aria-current` 当前区块语义与滚动同步更新。
- 待办：在桌面与移动端进行键盘流手工勾选确认。

---

## 6. WebDAV Critical Flow Checklist

Run sequence:
1. Test WebDAV
2. Check capabilities
3. Sync cache (with and without prune)
4. Filter by cache anomaly
5. Batch select cache anomaly
6. Execute batch action

Checks:
- [ ] Each step reports success/failure with actionable text.
- [ ] Sync-cache anomaly list links to repo pages correctly.
- [ ] Cache-anomaly filter matches latest sync result.
- [ ] Cache-anomaly batch selection enforces prerequisites (mode + snapshot).
- [ ] Non-WebDAV mode correctly disables cache-anomaly operations.

Notes:
- 代码层已完成关键链路提示与守卫：缓存异常筛选/批量选择受 WebDAV 模式与同步快照前置条件限制。
- 待办：使用真实 WebDAV 环境按 Run sequence 全链路走查，并勾选上述 5 项。
- 执行 runbook：`docs/plans/2026-03-01-gate3-webdav-critical-flow-runbook.md`。

---

## 7. Automated Regression Evidence

Run time (UTC+8): 2026-03-01 11:58 CST

Commands:

```bash
node --check github_release_watcher/static/app.js
node --check github_release_watcher/static/repo.js
python3 -m unittest tests.test_auth_security tests.test_downloader_behavior tests.test_state_robustness tests.test_watcher_webdav_parallel tests.test_watcher_webdav_stats_safety tests.test_webapp_api_smoke tests.test_webdav_reliability -v
```

Results:
- [x] JS checks pass.
- [x] Python regression suite passes.
- [ ] No unexpected warnings/errors requiring follow-up.

Evidence notes:
- `node --check github_release_watcher/static/app.js` passed.
- `node --check github_release_watcher/static/repo.js` passed.
- `python3 -m unittest tests.test_auth_security tests.test_downloader_behavior tests.test_state_robustness tests.test_watcher_webdav_parallel tests.test_watcher_webdav_stats_safety tests.test_webapp_api_smoke tests.test_webdav_reliability -v` passed (17 tests).
- 2026-03-01 12:00 CST rerun (after batch-toolbar disabled-reason polish): same command set passed.
- 2026-03-01 12:04 CST rerun (after aria-live accessibility polish): same command set passed.
- 2026-03-01 12:08 CST rerun (after mobile layout polish): same command set passed.
- 2026-03-01 12:08 CST rerun (after dialog focus-restore accessibility polish): same command set passed.
- 2026-03-01 12:11 CST rerun (after aria semantics and focus-visible polish): same command set passed.
- 2026-03-01 16:06 CST rerun (after mobile nav + dialog/touch ergonomics polish): same command set passed.
- Follow-up: `urllib3` reported `NotOpenSSLWarning` on local Python runtime (`LibreSSL 2.8.3`); does not block current functional checks.

---

## 8. Release Sign-off

- [ ] Checklist complete.
- [x] Known limitations documented.
- [x] Rollback plan prepared.

Rollback plan:
1. 回滚到上一个稳定提交（当前基线建议：`3522a7b` 之后的发布分支基线，或按发布标签回退）。
2. 保留并恢复 `config.override.json`、`state.json` 与下载目录数据，不做数据文件删除操作。
3. 仅回滚前端静态资源与文档提交时，先执行：
   - `node --check github_release_watcher/static/app.js`
   - `node --check github_release_watcher/static/repo.js`
4. 回滚后执行最小冒烟：
   - 登录 -> 首页加载 -> 单仓库“检查” -> 批量“检查” -> 设置页“测试 WebDAV”。

Approver: ________  
Date: ________
