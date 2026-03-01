# Gate 3 WebDAV 关键链路验收 Runbook

目标：对发布前 Gate 3 进行一次可追溯的端到端人工验收，覆盖 WebDAV 关键链路：
`测试连接 -> 能力探测 -> 同步缓存 -> 缓存异常筛选/选中 -> 批量动作`

---

## 1. 前置条件

- 服务已启动并可访问（可用脚本）：

```bash
scripts/qa/manual_acceptance_bootstrap.sh --config config.toml --host 127.0.0.1 --port 18000
```

- 设置中已切换到 `WebDAV` 存储模式。
- 已配置可访问的 WebDAV 地址与账号（建议独立测试目录）。
- 至少有 1~2 个可用于测试的启用仓库。

证据目录建议：
- `artifacts/manual-qa/<timestamp>/`

可选：自动生成本轮 Gate 3 验收报告（预填日期/提交号/证据目录）：

```bash
scripts/qa/new_gate3_report.sh
```

若希望一次性生成 Gate 2 + Gate 3 报告与总览导航：

```bash
scripts/qa/new_acceptance_packet.sh
```

---

## 2. 执行步骤与通过标准

### Step 1: 测试 WebDAV

操作：设置对话框点击「测试 WebDAV」。

通过标准：
- 页面出现明确成功/失败反馈；
- 失败时错误文案可定位问题（如认证失败、网络超时、TLS 问题）。

证据：
- 截图 `webdav-step1-test.png`

---

### Step 2: 检查能力

操作：点击「检查能力」。

通过标准：
- 能力提示文本更新成功；
- 不支持项会明确展示，文案可读。

证据：
- 截图 `webdav-step2-capabilities.png`

---

### Step 3: 同步缓存（先不 prune，再 prune）

操作：
1. 关闭 prune，点击「同步缓存」
2. 开启 prune，再点击一次「同步缓存」

通过标准：
- 每次都返回摘要（检查文件数、stale/missing、可选清理数量）；
- 有异常时能看到重点仓库信息，且链接可点击。

证据：
- 截图 `webdav-step3-sync-no-prune.png`
- 截图 `webdav-step3-sync-prune.png`

---

### Step 4: 缓存异常筛选

操作：回到仓库列表，状态筛选切换到「仅缓存异常」。

通过标准：
- 结果与最近一次同步缓存的异常仓库一致；
- 无异常时结果为空且提示合理。

证据：
- 截图 `webdav-step4-filter-cache-anomaly.png`

---

### Step 5: 选中缓存异常

操作：点击「选中缓存异常」。

通过标准：
- 在满足前置条件时能正确选中；
- 不满足前置条件时（非 WebDAV 或无同步快照）按钮禁用且原因清晰。

证据：
- 截图 `webdav-step5-select-cache-anomaly.png`
- 可选截图 `webdav-step5-disabled-reason.png`

---

### Step 6: 批量动作

操作：基于选中结果执行批量检查/启用/停用中的至少一项。

通过标准：
- 批量动作反馈与实际仓库状态一致；
- 对停用仓库的跳过统计准确。

证据：
- 截图 `webdav-step6-batch-action.png`

---

## 3. 失败判定

任一情况出现即判定 Gate 3 阻塞：
- 无法连通 WebDAV 或能力探测结果异常且无法解释；
- 同步缓存摘要与仓库筛选结果不一致；
- 缓存异常相关按钮守卫失效（该禁用未禁用，或原因缺失）；
- 批量动作结果与页面反馈不一致。

严重级别建议：
- 数据一致性/误操作风险：`P1/P2`
- 纯文案或可绕过交互问题：`P3/P4`

---

## 4. 验收记录模板

请优先使用完整模板：

- `docs/plans/2026-03-01-gate3-webdav-critical-flow-template.md`
- 或自动生成并预填的报告：`artifacts/manual-qa/<timestamp>/gate3-report.md`

---

## 5. 回填位置

完成后同步更新：
- `docs/plans/2026-03-01-release-acceptance-checklist.md`（第 6 节与 Gate 3 勾选）
- 如有缺陷，补充到缺陷跟踪（并标注 `P1/P2/P3/P4`）。
