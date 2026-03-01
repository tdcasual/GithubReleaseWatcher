# GitHub Release Watcher UI/Mobile/WebDAV Enhancement Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Upgrade the project from "usable" to "production-ready" by improving desktop/mobile UX, hardening WebDAV reliability, and adding safer operational controls.

**Architecture:** Keep current Python backend + static frontend architecture, but split responsibilities by module (API/auth/scheduler/storage/UI state). Add a WebDAV reliability layer (capability probe, retry/verify/concurrency control) and UI model updates that expose richer storage status and per-repo operations.

**Tech Stack:** Python 3.12, `requests`, built-in `http.server`, vanilla JS, CSS, unittest.

---

## Scope and Non-Goals

- In scope: UI/UX redesign, responsive mobile UX, WebDAV reliability, safety controls, tests, docs.
- Out of scope: complete framework migration (React/Vue), database rewrite (SQLite optional follow-up).

## API Change Set (planned)

1. `GET /api/v1/storage/capabilities`
- Returns detected WebDAV capabilities and health.

2. `GET /api/v1/storage/health`
- Returns upload queue stats, retry counters, recent failures.

3. `POST /api/v1/storage/sync-cache`
- Reconcile local cache with remote WebDAV metadata.

4. `POST /api/v1/cleanup/preview`
- Dry-run cleanup result before delete/remote remove.

5. `PUT /api/v1/settings` (extend payload)
- New fields under `storage.webdav`: `upload_concurrency`, `max_retries`, `retry_backoff_seconds`, `verify_after_upload`, `upload_temp_suffix`, `cleanup_mode`.

## Data Model Change Set (planned)

- Extend `state.json` repo stats:
  - `webdav_capabilities`
  - `upload_queue_depth`
  - `upload_retry_total`
  - `upload_verify_failed_total`
  - `cleanup_preview_last`

- Extend override config (`config.override.json`):
  - same WebDAV runtime fields as above.

## Milestones

1. Milestone A (Week 1-2): UI foundation + desktop UX
2. Milestone B (Week 3): mobile UX + responsive redesign
3. Milestone C (Week 4-5): WebDAV reliability + safety controls
4. Milestone D (Week 6): hardening, tests, docs, release checklist

---

### Task 1: Baseline and Safety Net

**Files:**
- Modify: `tests/test_download_integration.py`
- Create: `tests/test_webapp_api_smoke.py`
- Create: `tests/test_webdav_reliability.py`

**Step 1: Add smoke tests for existing API paths**
- Add tests for `/api/v1/status`, `/api/v1/repos`, `/api/v1/storage/test` basic behavior.

**Step 2: Run failing tests first**
Run: `python3 -m unittest tests/test_webapp_api_smoke.py -v`
Expected: FAIL (new tests without implementation helpers).

**Step 3: Add minimal harness (service bootstrap helpers)**
- Add shared helper to start/stop `WatcherService` with temp config.

**Step 4: Run and stabilize**
Run: `python3 -m unittest tests/test_webapp_api_smoke.py -v`
Expected: PASS.

**Step 5: Commit**
`git commit -m "test: add webapp smoke test harness"`

---

### Task 2: Auth and API Security Hardening

**Files:**
- Modify: `github_release_watcher/webapp.py`
- Modify: `github_release_watcher/static/app.js`
- Modify: `github_release_watcher/static/repo.js`
- Test: `tests/test_webapp_api_smoke.py`

**Step 1: Add first-login password change policy**
- Track default credentials state and reject sensitive API actions until password changed.

**Step 2: Add rate limiting for login**
- Per-IP short-window attempts; return `429` after threshold.

**Step 3: Harden cookie settings**
- Enable `Secure` when HTTPS or proxy header indicates TLS.

**Step 4: Restrict CORS policy**
- Remove wildcard default for authenticated endpoints.

**Step 5: Add tests**
Run: `python3 -m unittest tests/test_webapp_api_smoke.py -v`
Expected: PASS with cases for unauthorized, rate limit, first-login flow.

---

### Task 3: UI Design Tokens and Layout Refactor (Desktop first)

**Files:**
- Modify: `github_release_watcher/static/styles.css`
- Modify: `github_release_watcher/static/index.html`
- Modify: `github_release_watcher/static/app.js`

**Step 1: Introduce CSS token groups**
- Add semantic variables for surface, border, text, success/warn/error, spacing scale, shadow scale.

**Step 2: Create consistent layout primitives**
- Add utility classes for card sections, status strips, table/list wrappers, skeleton loaders.

**Step 3: Refactor dashboard sections**
- Convert current blocks into clear information hierarchy: summary row, repos table/card, activity timeline.

**Step 4: Add empty/loading/error states**
- Standardize placeholders across status, repo list, logs.

**Step 5: Verify with manual checks**
Run service and validate on 1366px and 1920px widths.

---

### Task 4: Repository UX Improvements (Desktop)

**Files:**
- Modify: `github_release_watcher/static/app.js`
- Modify: `github_release_watcher/static/index.html`
- Modify: `github_release_watcher/static/styles.css`

**Step 1: Add advanced repository controls**
- Add per-repo quick actions: run now, open detail, pause/resume, copy summary.

**Step 2: Add bulk operations**
- Enable multi-select and batch action for enable/disable and manual run.

**Step 3: Add client-side sorting/filtering chips**
- Status filters (all/healthy/error/network-error) and sort by next run, recent errors.

**Step 4: Add activity timeline grouping**
- Group events by day with compact tags.

**Step 5: Regression test (manual + smoke)**
Run: `python3 -m unittest tests/test_webapp_api_smoke.py -v`
Expected: PASS.

---

### Task 5: Mobile UI Redesign

**Files:**
- Modify: `github_release_watcher/static/styles.css`
- Modify: `github_release_watcher/static/index.html`
- Modify: `github_release_watcher/static/repo.html`
- Modify: `github_release_watcher/static/app.js`
- Modify: `github_release_watcher/static/repo.js`

**Step 1: Define responsive breakpoints**
- 320-479 (small phone), 480-767 (phone), 768-1023 (tablet), desktop fallback.

**Step 2: Add mobile navigation model**
- Sticky bottom nav/tabs for main actions on mobile.

**Step 3: Convert dense tables to card stacks**
- Repo and activity views become touch-first card layouts.

**Step 4: Improve touch accessibility**
- Ensure tap targets >= 44x44 px and dialog controls are thumb-friendly.

**Step 5: Mobile acceptance test checklist**
- iPhone SE width simulation, Android 360px width, tablet 768px.

---

### Task 6: Repo Detail Page Enhancement

**Files:**
- Modify: `github_release_watcher/static/repo.html`
- Modify: `github_release_watcher/static/repo.js`
- Modify: `github_release_watcher/static/styles.css`

**Step 1: Add health panels**
- Show release trend, last error root-cause, success ratio for checks/downloads.

**Step 2: Add collapsible sections on mobile**
- Activity and releases sections collapsible by default on small screens.

**Step 3: Add “copy diagnostic bundle” action**
- Include summary + latest errors + next schedule in one text payload.

**Step 4: Add repository-level run feedback states**
- Improve running/queued/failed states with badges.

**Step 5: Validate**
- Manual flow: open repo page -> run -> verify data refresh.

---

### Task 7: WebDAV Capability Probe

**Files:**
- Modify: `github_release_watcher/webdav.py`
- Modify: `github_release_watcher/webapp.py`
- Modify: `github_release_watcher/watcher.py`
- Test: `tests/test_webdav_reliability.py`

**Step 1: Add capability detection in `WebDAVClient`**
- Probe `PROPFIND`, `HEAD`, `MKCOL`, `PUT`, `DELETE`, optional `MOVE`.

**Step 2: Persist capability snapshot**
- Save probe output into repo stats for visibility.

**Step 3: Add API endpoint**
- Implement `GET /api/v1/storage/capabilities`.

**Step 4: Add tests for probe matrix**
- Mock different status code combinations.

**Step 5: Run tests**
Run: `python3 -m unittest tests/test_webdav_reliability.py -v`
Expected: PASS.

---

### Task 8: Reliable Upload Pipeline

**Files:**
- Modify: `github_release_watcher/webdav.py`
- Modify: `github_release_watcher/watcher.py`
- Modify: `github_release_watcher/config.py`
- Test: `tests/test_webdav_reliability.py`

**Step 1: Add temp-upload and finalize strategy**
- Upload to `<name>.uploading`, then finalize via `MOVE` or fallback copy+delete.

**Step 2: Add checksum/size verification**
- Verify remote size and record verification failures.

**Step 3: Add retry policy configuration**
- Support `max_retries`, `retry_backoff_seconds`, jitter.

**Step 4: Add queue depth telemetry**
- Record retries, queue depth, and failure classes.

**Step 5: Run tests**
Run: `python3 -m unittest tests/test_webdav_reliability.py -v`
Expected: PASS for retry/verify scenarios.

---

### Task 9: Upload Concurrency and Backpressure

**Files:**
- Modify: `github_release_watcher/watcher.py`
- Modify: `github_release_watcher/webapp.py`
- Modify: `github_release_watcher/config.py`
- Test: `tests/test_webdav_reliability.py`

**Step 1: Add bounded upload worker pool**
- Configurable `upload_concurrency` with safe defaults.

**Step 2: Add per-repo and global throttling**
- Prevent one repo from starving others.

**Step 3: Expose storage health API**
- Implement `GET /api/v1/storage/health`.

**Step 4: Add overload behavior tests**
- Ensure queue does not grow without bound and errors are reported cleanly.

**Step 5: Run tests**
Run: `python3 -m unittest tests/test_webdav_reliability.py -v`
Expected: PASS.

---

### Task 10: Safe Cleanup (Preview + Trash Mode)

**Files:**
- Modify: `github_release_watcher/watcher.py`
- Modify: `github_release_watcher/webapp.py`
- Modify: `github_release_watcher/static/app.js`
- Test: `tests/test_webdav_reliability.py`

**Step 1: Add cleanup preview API**
- Implement `POST /api/v1/cleanup/preview` returning planned deletions.

**Step 2: Add cleanup mode**
- Support `delete` (current) and `trash` (move to recycle path with timestamp).

**Step 3: Wire UI confirmation flow**
- Show affected tags/assets before saving cleanup-related settings.

**Step 4: Add tests**
- Verify preview accuracy and trash path safety rules.

**Step 5: Run tests**
Run: `python3 -m unittest tests/test_webdav_reliability.py -v`
Expected: PASS.

---

### Task 11: Config and State Robustness

**Files:**
- Modify: `github_release_watcher/config.py`
- Modify: `github_release_watcher/state.py`
- Modify: `github_release_watcher/webapp.py`
- Test: `tests/test_webapp_api_smoke.py`

**Step 1: Extend config schema validation**
- Validate new WebDAV fields and numeric bounds.

**Step 2: Harden `load_state` parsing**
- Catch JSON parse errors and auto-restore safe empty structure with backup rename.

**Step 3: Add migration path for new state fields**
- Ensure old state files remain readable.

**Step 4: Add tests for malformed state**
- Verify no crash on corrupted state file.

**Step 5: Run tests**
Run: `python3 -m unittest tests/test_webapp_api_smoke.py -v`
Expected: PASS.

---

### Task 12: Documentation, Verification, and Release Gate

**Files:**
- Modify: `README.md`
- Create: `docs/webdav-reliability.md`
- Create: `docs/mobile-ui-guidelines.md`
- Modify: `config.example.toml`

**Step 1: Document new API and config fields**
- Include examples for local mode and WebDAV mode.

**Step 2: Add operational runbook**
- Failure triage table for upload, verification, cleanup, auth lock.

**Step 3: Add release checklist**
- Smoke tests, mobile visual checks, WebDAV integration checks.

**Step 4: Full test run**
Run: `python3 -m unittest discover -s tests -p 'test_*.py' -v`
Expected: PASS on Python 3.12+.

**Step 5: Final commit**
`git commit -m "docs: add UI/mobile/WebDAV enhancement rollout plan"`

---

## Execution Order Recommendation

1. Task 1 -> 2 -> 11 (stability + safety baseline)
2. Task 3 -> 4 -> 5 -> 6 (UI and mobile)
3. Task 7 -> 8 -> 9 -> 10 (WebDAV reliability)
4. Task 12 (docs and release gate)

## Rollout Strategy

- Stage 1: Internal deployment with local storage mode only.
- Stage 2: WebDAV mode with `verify_after_upload=true`, `cleanup_mode=trash`.
- Stage 3: Enable deletion mode after 1 week error-free run.

## Done Criteria

- Mobile and desktop UI pass manual acceptance checklist.
- New WebDAV reliability tests pass consistently.
- No crash when state/config file is malformed.
- README reflects all new settings and APIs.
