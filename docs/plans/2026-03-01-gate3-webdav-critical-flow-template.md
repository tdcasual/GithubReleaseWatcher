# Gate 3 WebDAV 关键链路验收记录模板

执行日期：__________
执行人：__________
版本/提交：__________

环境：__________
配置文件：__________
证据目录：`artifacts/manual-qa/<timestamp>/`

---

## A. 前置条件确认

- [ ] 已启动 Web UI（`scripts/qa/manual_acceptance_bootstrap.sh`）
- [ ] 设置已切换到 WebDAV 模式
- [ ] WebDAV 账号与目录可访问
- [ ] 至少有 1~2 个启用仓库可用于链路验证

备注：
- ________

---

## B. 关键链路执行与结果

### Step 1: 测试 WebDAV

- [ ] Step 1 passed

通过标准：
- 点击“测试 WebDAV”后有明确结果。
- 失败时错误信息可定位（认证/超时/TLS/路径等）。

证据：
- [ ] `webdav-step1-test.png`

备注：
- ________

### Step 2: 检查能力

- [ ] Step 2 passed

通过标准：
- 能力提示有更新。
- 不支持项表达清晰。

证据：
- [ ] `webdav-step2-capabilities.png`

备注：
- ________

### Step 3: 同步缓存（不 prune + prune）

- [ ] Step 3 passed

通过标准：
- 两次同步均返回摘要（检查量、stale/missing、可选清理数量）。
- 有异常仓库时出现重点仓库信息及可点击链接。

证据：
- [ ] `webdav-step3-sync-no-prune.png`
- [ ] `webdav-step3-sync-prune.png`

备注：
- ________

### Step 4: 缓存异常筛选

- [ ] Step 4 passed

通过标准：
- “仅缓存异常”筛选结果与最近一次同步异常仓库一致。
- 无异常时结果为空且提示合理。

证据：
- [ ] `webdav-step4-filter-cache-anomaly.png`

备注：
- ________

### Step 5: 选中缓存异常

- [ ] Step 5 passed

通过标准：
- 前置条件满足时，“选中缓存异常”结果正确。
- 前置条件不满足时按钮禁用且原因准确。

证据：
- [ ] `webdav-step5-select-cache-anomaly.png`
- [ ] `webdav-step5-disabled-reason.png`（可选）

备注：
- ________

### Step 6: 批量动作

- [ ] Step 6 passed

通过标准：
- 批量动作反馈与实际状态一致。
- 对停用仓库的跳过数量正确。

证据：
- [ ] `webdav-step6-batch-action.png`

备注：
- ________

---

## C. 缺陷记录（如有）

| ID | Severity(P1-P4) | 现象 | 复现步骤 | 影响范围 | 状态 |
|---|---|---|---|---|---|
| DEF-WEBDAV-001 |  |  |  |  |  |

严重级别参考：
- `P1`：数据一致性或关键链路严重错误，发布阻塞。
- `P2`：关键链路可用性严重下降，发布阻塞。
- `P3`：存在替代路径的中等问题。
- `P4`：低影响文案/视觉问题。

---

## D. 结论

- [ ] Gate 3 pass
- [ ] Gate 3 blocked

结论说明：
- ________

后续动作：
- [ ] 已同步更新 `docs/plans/2026-03-01-release-acceptance-checklist.md` 第 6 节与 Gate 3 状态
- [ ] 已同步缺陷单（如存在）
