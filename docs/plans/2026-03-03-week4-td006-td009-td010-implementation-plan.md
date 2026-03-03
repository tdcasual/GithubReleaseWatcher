# Week4 TD-006 TD-009 TD-010 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 完成前端 bootstrap 契约收敛、安全基线升级（移除固定默认弱口令路径）、运行时观测指标扩展，满足 Week4 收口目标。

**Architecture:** 前端通过新增 `bootstrap-contract.js` 定义唯一启动契约并在 `app.js/repo.js` 强制校验。认证默认态改为“首次启动随机初始化口令 + 强制改密”，不再存在固定默认口令。指标层在 `MetricsRegistry` 扩展队列长度分布、运行时长分位与近期失败类型，并通过 `snapshot().metrics` 后向兼容输出。

**Tech Stack:** Python 3.12, pytest, Vanilla JS, bash.

---

### Task 1: TD-006 前端 bootstrap 契约收敛

**Files:**
- Create: `github_release_watcher/static/bootstrap-contract.js`
- Modify: `github_release_watcher/static/index.html`
- Modify: `github_release_watcher/static/repo.html`
- Modify: `github_release_watcher/static/app.js`
- Modify: `github_release_watcher/static/repo.js`
- Modify: `scripts/release/sync_vercel_public.sh`
- Modify: `tests/test_frontend_module_split.py`
- Create: `tests/test_frontend_bootstrap_contract.py`
- Modify: `tests/test_vercel_static_sync.py`

**Step 1: Write failing tests**

- 为 `bootstrap-contract.js` 增加契约测试：
  - 模块暴露 `window.GRWBootstrapContract`
  - 含契约版本号与模块校验函数
- 增加入口顺序测试：
  - `index.html` / `repo.html` 在入口脚本前加载 `bootstrap-contract.js`
- 增加入口使用测试：
  - `app.js` / `repo.js` 调用契约校验而非散落手工检查

**Step 2: Run tests to verify RED**

Run: `python3 -m pytest -q tests/test_frontend_module_split.py tests/test_frontend_bootstrap_contract.py tests/test_repo_page_shared_modules.py tests/test_vercel_static_sync.py`
Expected: fail because contract file/wiring not implemented.

**Step 3: Write minimal implementation**

- 新增 `bootstrap-contract.js`，提供统一 `requireModules`/`contract_version`。
- 在 `app.js`、`repo.js` 以契约方式检查依赖模块。
- 更新 `index.html`、`repo.html` 的脚本加载顺序。
- 更新同步脚本与 Vercel 同步检查列表，确保静态产物一致。

**Step 4: Run tests to verify GREEN**

Run: `python3 -m pytest -q tests/test_frontend_module_split.py tests/test_frontend_bootstrap_contract.py tests/test_repo_page_shared_modules.py tests/test_vercel_static_sync.py`
Expected: pass.

### Task 2: TD-009 安全基线收口（移除固定默认弱口令路径）

**Files:**
- Modify: `github_release_watcher/auth_service.py`
- Modify: `github_release_watcher/webapp.py`
- Modify: `github_release_watcher/static/index.html`
- Modify: `github_release_watcher/static/repo.html`
- Modify: `README.md`
- Modify: `tests/test_auth_security.py`
- Modify: `tests/test_webapp_api_smoke.py` (仅在需要时调整契约预期)

**Step 1: Write failing tests**

- 新增/调整测试，验证：
  - 缺省认证配置不再是固定 `admin/admin`
  - 缺省认证配置仍要求首次改密（`must_change_password=True`）
  - 认证字段可保留 `must_change_password`（避免 reload 后丢失）

**Step 2: Run tests to verify RED**

Run: `python3 -m pytest -q tests/test_auth_security.py tests/test_webapp_api_smoke.py`
Expected: fail because auth default strategy not upgraded yet.

**Step 3: Write minimal implementation**

- 将默认认证策略改为随机初始化口令（固定用户名 + 随机密码哈希）。
- `WatcherService` 在首次生成时持久化随机认证配置，并记录一次性启动提示日志。
- 保持 API 与设置流程兼容（登录/改密接口不破坏）。
- UI/文档把“默认 admin/admin”文案改为“首次初始化口令（见日志）”。

**Step 4: Run tests to verify GREEN**

Run: `python3 -m pytest -q tests/test_auth_security.py tests/test_webapp_api_smoke.py tests/test_webapp_end_to_end_minimal.py`
Expected: pass.

### Task 3: TD-010 运行时指标扩展

**Files:**
- Modify: `github_release_watcher/metrics.py`
- Modify: `github_release_watcher/run_queue.py`
- Modify: `github_release_watcher/webapp.py`
- Modify: `tests/test_runtime_metrics.py`
- Create: `tests/test_runtime_metrics_extended.py`
- Modify: `tests/snapshots/status_shape.json`
- Modify: `tests/test_webapp_api_contract.py` (仅在快照变化需要时)

**Step 1: Write failing tests**

- 增加扩展指标测试：
  - 队列长度实时/峰值与桶统计字段
  - 运行耗时分位字段（如 p50/p95）
  - 最近失败类型计数字段
- 保留旧字段断言，确保后向兼容。

**Step 2: Run tests to verify RED**

Run: `python3 -m pytest -q tests/test_runtime_metrics.py tests/test_runtime_metrics_extended.py tests/test_webapp_api_contract.py`
Expected: fail because new metric fields not implemented.

**Step 3: Write minimal implementation**

- `MetricsRegistry` 新增：
  - 队列长度观测（current/peak/buckets）
  - 运行耗时记录与近窗分位计算
  - 失败类型近窗计数
- 在 `RunQueueService` 与 `WatcherService._do_run_once` 接入指标上报。
- 更新 `status_shape.json` 以覆盖新增字段类型。

**Step 4: Run tests to verify GREEN**

Run: `python3 -m pytest -q tests/test_runtime_metrics.py tests/test_runtime_metrics_extended.py tests/test_webapp_api_contract.py`
Expected: pass.

### Task 4: Week4 回归验收

**Files:**
- Modify: none expected

**Step 1: Frontend + Contract regression**

Run: `python3 -m pytest -q tests/test_frontend_module_split.py tests/test_frontend_bootstrap_contract.py tests/test_repo_page_shared_modules.py tests/test_vercel_static_sync.py`
Expected: pass.

**Step 2: Security + API regression**

Run: `python3 -m pytest -q tests/test_auth_security.py tests/test_webapp_api_smoke.py tests/test_webapp_end_to_end_minimal.py`
Expected: pass.

**Step 3: Metrics + API contract regression**

Run: `python3 -m pytest -q tests/test_runtime_metrics.py tests/test_runtime_metrics_extended.py tests/test_webapp_api_contract.py`
Expected: pass.

**Step 4: Stable regression + syntax checks**

Run: `python3 -m pytest -q -k "not download_integration"`
Run: `for action in github_release_watcher/static/*.js deploy/vercel/public/*.js; do node --check "$action"; done`
Expected: all pass.
