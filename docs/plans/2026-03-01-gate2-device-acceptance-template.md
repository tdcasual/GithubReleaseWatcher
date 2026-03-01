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

---

## F. 结论

- [ ] Gate 2 pass
- [ ] Gate 2 blocked

结论说明：
- ________
