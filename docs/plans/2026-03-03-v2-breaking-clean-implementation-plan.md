# V2 Breaking-Clean Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the V2 backend skeleton (`FastAPI + SQLite job/event model`) as the first concrete migration slice, without adding V1 runtime compatibility.

**Architecture:** Introduce a new `github_release_watcher.v2` package isolated from V1 runtime code. Start with an app factory, a V2 health route, a SQLite schema bootstrap module, and a minimal jobs API (`enqueue/list`) backed by a repository layer. Keep V2 endpoints under `/api/v2/*` and avoid reusing V1 request/response contracts.

**Tech Stack:** Python 3.12+ target runtime, FastAPI, stdlib `sqlite3`, pytest.

---

### Task 1: Add V2 app factory and health endpoint

**Files:**
- Create: `tests/test_v2_app_health.py`
- Create: `github_release_watcher/v2/__init__.py`
- Create: `github_release_watcher/v2/app.py`

**Step 1: Write the failing test**

- Add test that imports `create_app()` and asserts:
  - `GET /api/v2/health` returns `200`
  - payload includes `ok: true`
  - payload includes `api_version: "v2"`

**Step 2: Run test to verify RED**

Run: `python3 -m pytest -q tests/test_v2_app_health.py`  
Expected: FAIL (`ModuleNotFoundError` or missing `create_app`/route).

**Step 3: Write minimal implementation**

- Implement `create_app()` in `github_release_watcher/v2/app.py`.
- Register `/api/v2/health`.

**Step 4: Run test to verify GREEN**

Run: `python3 -m pytest -q tests/test_v2_app_health.py`  
Expected: PASS.

### Task 2: Add V2 SQLite schema bootstrap

**Files:**
- Create: `tests/test_v2_db_bootstrap.py`
- Create: `github_release_watcher/v2/db.py`

**Step 1: Write the failing test**

- Add test that:
  - creates temporary sqlite file
  - calls `init_db(path)`
  - verifies tables `repos`, `jobs`, `events` exist
  - verifies `jobs.status` constrained to `queued|running|succeeded|failed|canceled`

**Step 2: Run test to verify RED**

Run: `python3 -m pytest -q tests/test_v2_db_bootstrap.py`  
Expected: FAIL (`ModuleNotFoundError` or missing function/schema).

**Step 3: Write minimal implementation**

- Implement `init_db(db_path)` in `github_release_watcher/v2/db.py`.
- Create schema via `CREATE TABLE IF NOT EXISTS ...`.

**Step 4: Run test to verify GREEN**

Run: `python3 -m pytest -q tests/test_v2_db_bootstrap.py`  
Expected: PASS.

### Task 3: Add V2 jobs repository and API endpoints

**Files:**
- Create: `tests/test_v2_jobs_api.py`
- Create: `github_release_watcher/v2/jobs.py`
- Modify: `github_release_watcher/v2/app.py`

**Step 1: Write the failing test**

- Add test that:
  - creates app with temporary sqlite db
  - `POST /api/v2/jobs` with `{ "kind": "run_repos", "payload": {"repos": ["owner/repo"]} }`
  - expects `201` and returned `status: queued`
  - `GET /api/v2/jobs` returns at least one queued job.

**Step 2: Run test to verify RED**

Run: `python3 -m pytest -q tests/test_v2_jobs_api.py`  
Expected: FAIL (route or persistence missing).

**Step 3: Write minimal implementation**

- Implement jobs repository (`enqueue_job`, `list_jobs`) in `jobs.py`.
- Wire routes in app:
  - `POST /api/v2/jobs`
  - `GET /api/v2/jobs`

**Step 4: Run test to verify GREEN**

Run: `python3 -m pytest -q tests/test_v2_jobs_api.py`  
Expected: PASS.

### Task 4: Add V2 startup CLI entrypoint

**Files:**
- Create: `tests/test_v2_cli.py`
- Modify: `github_release_watcher/cli.py`
- Modify: `README.md`

**Steps:**
1. Add failing test for `--web-v2` argument handling.
2. Verify RED.
3. Implement `--web-v2` to start `create_app()` with uvicorn-compatible app object exposure.
4. Verify GREEN.

### Task 5: Add V2 auth/session baseline

**Files:**
- Create: `tests/test_v2_auth.py`
- Create: `github_release_watcher/v2/auth.py`
- Modify: `github_release_watcher/v2/app.py`

**Steps:**
1. Add failing tests for login, cookie session issuance, unauthorized access rejection.
2. Verify RED.
3. Implement minimal auth/session flow for V2 endpoints.
4. Verify GREEN.

### Task 6: Add V2 event stream API

**Files:**
- Create: `tests/test_v2_events_api.py`
- Modify: `github_release_watcher/v2/jobs.py`
- Modify: `github_release_watcher/v2/app.py`

**Steps:**
1. Add failing tests for job event append and `/api/v2/events` read.
2. Verify RED.
3. Implement repository/event API.
4. Verify GREEN.

### Task 7: Introduce V1 deletion guardrails in CI (pre-delete stage)

**Files:**
- Modify: `.github/workflows/ci.yml`
- Create: `tests/test_v2_guardrails.py`

**Steps:**
1. Add failing tests that enforce V2 route prefix usage for new APIs and block new V1 compatibility fields.
2. Verify RED.
3. Implement CI checks and tests.
4. Verify GREEN.

### Task 8: Phase verification

**Commands:**
- `python3 -m pytest -q tests/test_v2_app_health.py tests/test_v2_db_bootstrap.py tests/test_v2_jobs_api.py`
- `python3 -m pytest -q -k "not download_integration"`
- `for f in github_release_watcher/static/*.js deploy/vercel/public/*.js; do node --check "$f"; done`

