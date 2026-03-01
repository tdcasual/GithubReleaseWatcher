# GitHub Release Watcher Release Polish Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move current UI/interaction work from "feature-complete" to "release-ready" with explicit quality gates for desktop/mobile UX, WebDAV workflows, and regression safety.

**Architecture:** Keep the current architecture (Python backend + static web frontend) and execute a strict "no new feature" stabilization pass. Focus on UI consistency, mobile behavior, accessibility basics, and operational reliability visibility. Use a checklist-driven release gate to prevent subjective "looks done" decisions.

**Tech Stack:** Python 3.12, built-in `http.server`, vanilla JS, CSS, `unittest`, git.

---

## Scope Freeze

- In scope: UI consistency, mobile UX fixes, error/loading/empty-state polish, accessibility baseline, WebDAV workflow clarity, release checklist and evidence.
- Out of scope: new backend capabilities, data model expansion, framework migration, large visual redesign.
- Rule: any new scope request must be logged and explicitly accepted before implementation.

## Release Gates

- Gate 1: No `P1/P2` open defects.
- Gate 2: Core flows pass on desktop and mobile checklist.
- Gate 3: WebDAV critical flow passes end-to-end (`test -> capabilities -> sync-cache -> filter/select -> batch action`).
- Gate 4: Regression command set passes with fresh evidence.

---

### Task 1: Freeze Baseline and Tracking

**Files:**
- Create: `docs/plans/2026-03-01-release-acceptance-checklist.md`
- Modify: `README.md`

**Step 1: Create release checklist document**
- Add sections for quality gates, manual test matrix, defect severity definitions, and sign-off.

**Step 2: Add README navigation entry**
- Add a concise section linking polish plan and acceptance checklist.

**Step 3: Commit**
```bash
git add docs/plans/2026-03-01-release-polish-plan.md docs/plans/2026-03-01-release-acceptance-checklist.md README.md
git commit -m "docs: add release polish plan and acceptance checklist"
```

---

### Task 2: Desktop UI Consistency Sweep

**Files:**
- Modify: `github_release_watcher/static/index.html`
- Modify: `github_release_watcher/static/styles.css`
- Modify: `github_release_watcher/static/app.js`

**Step 1: Build a UI inconsistency checklist from key pages**
- Status card, repo list, batch toolbar, settings dialog, logs.

**Step 2: Normalize component behavior**
- Standardize disabled-state feedback, tooltip/help text, and success/failure hint style.

**Step 3: Verify manually**
- Check at `1366x768` and `1920x1080`.

**Step 4: Run syntax checks**
```bash
node --check github_release_watcher/static/app.js
node --check github_release_watcher/static/repo.js
```

**Step 5: Commit**
```bash
git add github_release_watcher/static/index.html github_release_watcher/static/styles.css github_release_watcher/static/app.js
git commit -m "fix: polish desktop ui consistency and state feedback"
```

---

### Task 3: Mobile UX Acceptance and Fixes

**Files:**
- Modify: `github_release_watcher/static/styles.css`
- Modify: `github_release_watcher/static/index.html`
- Modify: `github_release_watcher/static/repo.html`
- Modify: `github_release_watcher/static/repo.js`

**Step 1: Run mobile checklist**
- Test iOS Safari and Android Chrome for touch targets, wrapping, dialog actions, and scroll behavior.

**Step 2: Fix layout/interaction defects**
- Prioritize clipped controls, overlapping sticky regions, and hard-to-tap actions.

**Step 3: Capture evidence**
- Add checklist result entries with device/browser/version.

**Step 4: Run syntax checks**
```bash
node --check github_release_watcher/static/app.js
node --check github_release_watcher/static/repo.js
```

**Step 5: Commit**
```bash
git add github_release_watcher/static/styles.css github_release_watcher/static/index.html github_release_watcher/static/repo.html github_release_watcher/static/repo.js docs/plans/2026-03-01-release-acceptance-checklist.md
git commit -m "fix: resolve mobile ux acceptance issues"
```

---

### Task 4: Accessibility Baseline Pass

**Files:**
- Modify: `github_release_watcher/static/index.html`
- Modify: `github_release_watcher/static/repo.html`
- Modify: `github_release_watcher/static/styles.css`
- Modify: `github_release_watcher/static/app.js`
- Modify: `github_release_watcher/static/repo.js`

**Step 1: Keyboard and focus audit**
- Ensure all key actions are reachable by keyboard and focus ring is visible.

**Step 2: Semantic/ARIA cleanup**
- Improve labels and `aria-*` for status hints, dialogs, and toolbar actions where needed.

**Step 3: Color contrast and error readability**
- Confirm error/warn text remains readable in both light and dark schemes.

**Step 4: Manual verify**
- Keyboard-only pass for login, status card controls, repo filtering, and batch actions.

**Step 5: Commit**
```bash
git add github_release_watcher/static/index.html github_release_watcher/static/repo.html github_release_watcher/static/styles.css github_release_watcher/static/app.js github_release_watcher/static/repo.js docs/plans/2026-03-01-release-acceptance-checklist.md
git commit -m "fix: improve accessibility baseline for web ui"
```

---

### Task 5: WebDAV Workflow Clarity and Guardrails

**Files:**
- Modify: `github_release_watcher/static/app.js`
- Modify: `github_release_watcher/static/index.html`
- Modify: `README.md`

**Step 1: Validate WebDAV diagnostics flow messaging**
- Confirm each stage has clear next action text on success/failure.

**Step 2: Improve guardrails**
- Ensure cache-anomaly features clearly indicate prerequisites and invalid states.

**Step 3: Manual end-to-end run**
- `测试 WebDAV -> 检查能力 -> 同步缓存 -> 缓存异常筛选/选中 -> 批量动作`.

**Step 4: Commit**
```bash
git add github_release_watcher/static/app.js github_release_watcher/static/index.html README.md docs/plans/2026-03-01-release-acceptance-checklist.md
git commit -m "fix: polish webdav workflow guidance and guardrails"
```

---

### Task 6: Regression and Release Gate Verification

**Files:**
- Modify: `docs/plans/2026-03-01-release-acceptance-checklist.md`

**Step 1: Run required automated verification**
```bash
node --check github_release_watcher/static/app.js
node --check github_release_watcher/static/repo.js
python3 -m unittest tests.test_auth_security tests.test_downloader_behavior tests.test_state_robustness tests.test_watcher_webdav_parallel tests.test_watcher_webdav_stats_safety tests.test_webapp_api_smoke tests.test_webdav_reliability -v
```

**Step 2: Record evidence**
- Add command outputs summary, timestamp, and pass/fail status in checklist.

**Step 3: Confirm release gates**
- Explicitly mark Gate 1-4 pass/fail with notes.

**Step 4: Commit**
```bash
git add docs/plans/2026-03-01-release-acceptance-checklist.md
git commit -m "docs: record release gate verification evidence"
```

---

### Task 7: Release Packaging

**Files:**
- Modify: `README.md`
- Modify: `docs/plans/2026-03-01-release-acceptance-checklist.md`

**Step 1: Final docs sanity**
- Ensure user-facing docs match current behavior.

**Step 2: Write release notes summary**
- Include major UX/WebDAV improvements and known limitations.

**Step 3: Tag/release handoff prep**
- Prepare release message and rollback note.

**Step 4: Commit**
```bash
git add README.md docs/plans/2026-03-01-release-acceptance-checklist.md
git commit -m "docs: finalize release notes and handoff checklist"
```

---

## Execution Order

1. Task 1 (baseline docs and checklist)
2. Task 2 (desktop consistency)
3. Task 3 (mobile acceptance)
4. Task 4 (accessibility baseline)
5. Task 5 (WebDAV flow clarity)
6. Task 6 (regression evidence)
7. Task 7 (release packaging)

## Blocking Conditions

- Any `P1` defect blocks release immediately.
- Any failing test in required command set blocks release.
- Any unknown behavior in WebDAV end-to-end flow blocks release until reproduced and documented.

