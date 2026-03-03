# Week2 TD-003 TD-005 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extract query/diagnostics responsibilities from `WatcherService` and unify config validation rules across config + payload + overrides/settings paths.

**Architecture:** Introduce two focused backend services (`RepoQueryService`, `StorageHealthService`) and delegate heavy read/query logic from `WatcherService` to these services. Introduce a shared `config_validation` module and make `config.py` + `webapp_payloads.py` consume the same normalization/range/suffix rules, while preserving API response shapes and existing compatibility fields.

**Tech Stack:** Python 3.12, pytest, existing stdlib HTTP server, existing config/overrides pipeline.

---

### Task 1: TD-003 service extraction (repo query + storage health)

**Files:**
- Create: `github_release_watcher/repo_query_service.py`
- Create: `github_release_watcher/storage_health_service.py`
- Modify: `github_release_watcher/webapp.py`
- Test: `tests/test_repo_query_service.py`
- Test: `tests/test_storage_health_service.py`

**Step 1: Write failing tests**

- Add tests for repo summaries/detail/activity/releases behaviors in `tests/test_repo_query_service.py`.
- Add tests for storage health aggregation and cache sync/prune behaviors in `tests/test_storage_health_service.py`.

**Step 2: Run tests to verify RED**

Run: `python3 -m pytest -q tests/test_repo_query_service.py tests/test_storage_health_service.py`
Expected: fail with import/module errors (new services not yet implemented).

**Step 3: Write minimal implementation**

- Implement `RepoQueryService` by moving read-only query logic from `WatcherService`.
- Implement `StorageHealthService` by moving storage totals + cache sync logic.
- Update `WatcherService` to delegate to these services without changing API payload schema.

**Step 4: Run tests to verify GREEN**

Run: `python3 -m pytest -q tests/test_repo_query_service.py tests/test_storage_health_service.py tests/test_webapp_api_contract.py tests/test_webapp_api_smoke.py`
Expected: pass.

### Task 2: TD-005 unified validation module

**Files:**
- Create: `github_release_watcher/config_validation.py`
- Modify: `github_release_watcher/config.py`
- Modify: `github_release_watcher/webapp_payloads.py`
- Test: `tests/test_config_validation_unified.py`
- Test: `tests/test_settings_service.py`
- Test: `tests/test_webdav_reliability.py`
- Test: `tests/test_config_unknown_keys.py`

**Step 1: Write failing tests**

- Add `tests/test_config_validation_unified.py` validating shared normalization/range logic (storage mode, asset types, upload temp suffix, cleanup mode, timeout range).

**Step 2: Run tests to verify RED**

Run: `python3 -m pytest -q tests/test_config_validation_unified.py`
Expected: fail because shared module and/or integrated behavior is not yet present.

**Step 3: Write minimal implementation**

- Implement shared validators in `config_validation.py`.
- Replace duplicated logic in `webapp_payloads.py` with wrappers around shared validators.
- Update `config.py` to use shared validators for storage mode, asset type normalization, suffix/cleanup checks, and webdav timeout range.

**Step 4: Run tests to verify GREEN**

Run: `python3 -m pytest -q tests/test_config_validation_unified.py tests/test_settings_service.py tests/test_webdav_reliability.py tests/test_config_unknown_keys.py`
Expected: pass.

### Task 3: full regression and contract safety

**Files:**
- Modify: none expected (verification task)
- Test: `tests/test_line_budgets.py`
- Test: `tests/test_ci_checks_modules.py`

**Step 1: Run full stable suite**

Run: `python3 -m pytest -q -k "not download_integration"`
Expected: pass.

**Step 2: Run frontend syntax checks**

Run: `for action in github_release_watcher/static/*.js deploy/vercel/public/*.js; do node --check "$action"; done`
Expected: pass.

**Step 3: Verify forbidden tracked artifacts**

Run: `git ls-files | rg '^\.playwright-cli/|^config\.toml$|^real_state 2\.json$'`
Expected: no output.
