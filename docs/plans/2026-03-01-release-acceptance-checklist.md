# Release Acceptance Checklist (UI/Mobile/WebDAV)

Last update: 2026-03-01  
Owner: Maintainer

---

## 1. Quality Gates

- [ ] Gate 1: No open `P1/P2` defects.
- [ ] Gate 2: Core user flows pass on desktop and mobile.
- [ ] Gate 3: WebDAV critical flow passes end-to-end.
- [ ] Gate 4: Required automated regression commands pass.

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
- ________

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
- ________

---

## 5. Accessibility Baseline Checklist

- [ ] Keyboard-only navigation reaches all major controls.
- [ ] Focus indicators are visible on actionable controls.
- [ ] Dialog focus behavior and close behavior are consistent.
- [ ] Error/warn text remains readable in light/dark modes.
- [ ] Critical controls have clear labels/aria semantics.

Notes:
- ________

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
- ________

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
- Follow-up: `urllib3` reported `NotOpenSSLWarning` on local Python runtime (`LibreSSL 2.8.3`); does not block current functional checks.

---

## 8. Release Sign-off

- [ ] Checklist complete.
- [ ] Known limitations documented.
- [ ] Rollback plan prepared.

Approver: ________  
Date: ________
