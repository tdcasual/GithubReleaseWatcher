# Week3 TD-004 TD-007 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add state schema migration path to avoid silent state reset, and add behavior-level minimal end-to-end regression coverage for core API flow.

**Architecture:** Introduce dedicated state migration module and keep `load_state` as the single read entry that attempts deterministic migration when possible and falls back safely when not. Add one in-process end-to-end API test and one deterministic smoke script to validate login/state/run/repos behavior path without external dependencies.

**Tech Stack:** Python 3.12, stdlib HTTP server/client, pytest, shell script (`bash`).

---

### Task 1: TD-004 state migration chain

**Files:**
- Create: `github_release_watcher/state_migrations.py`
- Modify: `github_release_watcher/state.py`
- Test: `tests/test_state_migrations.py`
- Test: `tests/test_state_robustness.py`

**Step 1: Write failing tests**

- Add migration tests to validate:
  - v1 state migrates to latest version and preserves repo data.
  - migration metadata is recorded for diagnostics.
  - non-migratable versions fall back to empty state safely.

**Step 2: Run tests to verify RED**

Run: `python3 -m pytest -q tests/test_state_migrations.py tests/test_state_robustness.py`
Expected: fail because migration module/path is not implemented yet.

**Step 3: Write minimal implementation**

- Implement migration registry and v1->v2 migration.
- Update `load_state` to:
  - parse + validate raw JSON
  - attempt migration when version mismatched
  - preserve corrupted-file backup behavior
  - fallback to empty state if migration cannot be performed.

**Step 4: Run tests to verify GREEN**

Run: `python3 -m pytest -q tests/test_state_migrations.py tests/test_state_robustness.py`
Expected: pass.

### Task 2: TD-007 behavior-level regression coverage

**Files:**
- Create: `tests/test_webapp_end_to_end_minimal.py`
- Create: `scripts/qa/smoke_api_flow.sh`
- Modify: `README.md` (QA script section)

**Step 1: Write failing test**

- Add one minimal end-to-end test flow:
  - login -> read state -> trigger run -> query repos.
- Ensure assertions focus on behavior/status fields rather than source-text string contains.

**Step 2: Run tests to verify RED**

Run: `python3 -m pytest -q tests/test_webapp_end_to_end_minimal.py`
Expected: fail because test file/new flow not implemented yet.

**Step 3: Write minimal implementation**

- Implement in-process deterministic e2e test using `_Server` + `http.client`.
- Add `scripts/qa/smoke_api_flow.sh` that runs an equivalent flow in a temporary workspace and exits non-zero on failure.
- Update README to mention the new smoke script.

**Step 4: Run tests to verify GREEN**

Run: `python3 -m pytest -q tests/test_webapp_end_to_end_minimal.py tests/test_webapp_api_smoke.py`
Expected: pass.

### Task 3: Full verification

**Files:**
- Modify: none expected (verification task)

**Step 1: Run stable regression**

Run: `python3 -m pytest -q -k "not download_integration"`
Expected: pass.

**Step 2: Run smoke script**

Run: `bash scripts/qa/smoke_api_flow.sh`
Expected: script exits 0 and prints all checkpoint success lines.

**Step 3: Run frontend syntax checks**

Run: `for action in github_release_watcher/static/*.js deploy/vercel/public/*.js; do node --check "$action"; done`
Expected: pass.
