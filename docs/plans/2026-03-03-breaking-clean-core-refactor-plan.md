# Breaking Clean Core Refactor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在不保留历史兼容层的前提下，清理运行队列 API、移除过渡别名、提升调度线程健壮性、收敛状态迁移风险，并减少查询路径的耦合与重复读取。

**Architecture:** 采用“先测后改”的破坏式重构路径：先把对外契约切换为单一语义（`queue_status`），再清除内部兼容别名（`_queue` / `enqueue` bool 语义），同时将调度线程改为异常隔离循环避免单点崩溃。状态层从“静默回空”改为“先备份后重置”，优先保证可恢复性。查询层改为显式接收 state snapshot，减少隐式 I/O。

**Tech Stack:** Python 3.12+, pytest/unittest, vanilla JS modules, built-in http.server

---

### Task 1: Remove run API compatibility field and bool enqueue compatibility

**Files:**
- Modify: `github_release_watcher/run_queue.py`
- Modify: `github_release_watcher/webapp.py`
- Modify: `github_release_watcher/webapp_api_router.py`
- Modify: `tests/test_run_queue.py`
- Modify: `tests/test_webapp_api_smoke.py`
- Modify: `tests/test_webapp_end_to_end_minimal.py`

### Task 2: Make scheduler loop crash-safe under config/runtime errors

**Files:**
- Modify: `github_release_watcher/webapp.py`
- Modify: `tests/test_webapp_api_smoke.py`

### Task 3: Harden state migration failure handling with backup-before-reset

**Files:**
- Modify: `github_release_watcher/state.py`
- Modify: `tests/test_state_migrations.py`

### Task 4: Decouple repo query from implicit load_state IO

**Files:**
- Modify: `github_release_watcher/repo_query_service.py`
- Modify: `github_release_watcher/webapp.py`
- Modify: `tests/test_repo_query_service.py`

### Task 5: Frontend queue status single-source semantics

**Files:**
- Modify: `github_release_watcher/static/app-runtime.js`
- Modify: `github_release_watcher/static/repo.js`
- Modify: `github_release_watcher/static/batch-actions.js`
- Modify: `README.md`
- Run: `scripts/release/sync_vercel_public.sh`

### Task 6: Verification

**Commands:**
- `python3 -m pytest -q tests/test_run_queue.py tests/test_webapp_api_smoke.py tests/test_webapp_end_to_end_minimal.py tests/test_state_migrations.py tests/test_repo_query_service.py`
- `python3 -m pytest -q -k "not download_integration"`
- `for f in github_release_watcher/static/*.js deploy/vercel/public/*.js; do node --check "$f"; done`
