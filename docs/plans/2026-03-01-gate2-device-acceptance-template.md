# Gate 2 真机验收记录模板（Desktop + Mobile）

执行日期：__________
执行人：__________
版本/提交：__________

证据目录：`artifacts/manual-qa/<timestamp>/`

---

## A. 环境信息

### Desktop
- OS：__________
- Browser + version：__________
- Screen size(s)：__________

### Mobile Device 1
- Device：__________
- Browser/version：__________

### Mobile Device 2
- Device：__________
- Browser/version：__________

---

## B. Desktop 检查项

- [ ] Login flow works and security banner behavior is correct.
- [ ] Status card numbers/time text update correctly after operations.
- [ ] Repo search + state filter + sort combinations behave consistently.
- [ ] Batch actions (`select/invert/enabled/error/cache-anomaly/run/enable/disable/clear`) match visible data.
- [ ] Disabled buttons include clear reason where applicable.
- [ ] Settings dialog actions (`test/capabilities/sync-cache/cleanup-preview/save`) produce clear feedback.
- [ ] Logs section remains readable and copy action works.

Desktop 判定标准（快速判断）：
- 登录流程：`通过` = 登录成功后主界面可操作，安全横幅逻辑符合当前账号状态；`失败` = 登录后仍停留对话框或安全横幅状态错误。
- 状态卡更新：`通过` = 触发操作后时间/范围字段有可解释变化；`失败` = 字段长期不变或出现明显错误值。
- 筛选/排序一致性：`通过` = 组合切换后仓库集合与顺序可预测；`失败` = 出现“筛选条件不生效/排序反复跳动”。
- 批量动作一致性：`通过` = 批量操作结果与已选仓库一致；`失败` = 未选仓库被影响或选中仓库未被处理。
- 禁用原因：`通过` = 禁用按钮有明确原因提示；`失败` = 禁用但无解释，或提示与实际条件不符。
- 设置对话框反馈：`通过` = 每个动作都有成功/失败文本；`失败` = 无反馈、反馈位置不可见或文案无法定位问题。
- 日志可读与复制：`通过` = 日志不重叠、复制结果可粘贴；`失败` = 文本截断严重或复制内容为空。

Desktop 备注：
- ________

---

## C. Mobile 检查项

- [ ] Topbar and status card remain readable without overlap.
- [ ] Batch toolbar buttons are tappable and wrap correctly.
- [ ] Repo card controls do not clip or overlap.
- [ ] Dialog actions are reachable and readable at small widths.
- [ ] Scroll behavior is stable when dialogs open/close.
- [ ] Touch target sizes are acceptable for main actions.

Mobile 判定标准（快速判断）：
- Topbar/状态卡：`通过` = 无重叠、无遮挡、主要按钮可触达；`失败` = 顶部信息互相压盖或关键按钮不可点。
- 批量工具栏：`通过` = 按钮可换行且无裁切；`失败` = 文本溢出、按钮重叠或点击命中困难。
- Repo 卡控件：`通过` = 选中、检查、活动、启用开关都可稳定触发；`失败` = 控件挤压导致误触/漏触。
- 对话框动作：`通过` = 小屏可滚动到所有操作按钮，按钮文案完整；`失败` = 按钮被遮挡或无法到达。
- 弹窗滚动稳定性：`通过` = 弹窗打开时背景不乱滚，关闭后回到原上下文；`失败` = 视图跳动或底部导航误触。
- 触控目标：`通过` = 主要按钮有足够点击面积（建议 40px+）；`失败` = 高频操作需要精确点按才能触发。

Mobile 备注：
- ________

---

## D. Accessibility 快速抽检

- [ ] Keyboard-only navigation reaches all major controls.
- [ ] Focus indicators are visible on actionable controls.
- [ ] Dialog focus behavior and close behavior are consistent.

备注：
- ________

---

## E. 缺陷记录（如有）

| ID | Severity(P1-P4) | 现象 | 复现步骤 | 影响范围 | 状态 |
|---|---|---|---|---|---|
| DEF-001 |  |  |  |  |  |

严重级别参考：
- `P1`：数据错误、错误操作不可恢复、核心流程阻断。
- `P2`：核心功能可用性严重下降，发布不应继续。
- `P3`：有替代路径的中等问题，可记录后发布。
- `P4`：低风险视觉或文案问题。

---

## F. 结论

- [ ] Gate 2 pass
- [ ] Gate 2 blocked

结论说明：
- ________
