# 2026-03-02 Architecture Refactor Roadmap

## Goal
在不牺牲当前可用性的前提下，完成项目从“功能型单体”向“分层单体”的重构，降低 `webapp.py` / `static/app.js` 的复杂度，提高后续扩展与测试效率。

## Baseline
- Latest UI/runtime baseline commits:
  - `b2a5a06` feat(ui): improve mobile layout and structured activity logs
  - `5616679` test(ui): add regression guards for mobile and logs readability
- Current regression command:
  - `python3 -m pytest -q`

## Phase Plan

### Phase 1: Backend extraction (no behavior change)
目标：拆分 `webapp.py`，先迁移可独立模块化的纯职责组件。

1. Commit A: Extract auth service module
- Create `github_release_watcher/auth_service.py`
- Move auth hashing/config/session logic out of `webapp.py`
- Keep public compatibility: `webapp.AuthService`, `webapp._load_auth_config` remain importable
- Verification:
  - `python3 -m pytest -q tests/test_auth_security.py tests/test_webapp_api_smoke.py`

2. Commit B: Extract API payload normalization helpers
- Create `github_release_watcher/webapp_payloads.py`
- Move `_safe_int`, asset type normalization, regex normalization, storage mode normalization
- Verification:
  - `python3 -m pytest -q tests/test_webapp_api_smoke.py`

3. Commit C: Extract override apply logic
- Create `github_release_watcher/webapp_overrides.py`
- Move `_apply_overrides` and path resolution helpers
- Verification:
  - `python3 -m pytest -q tests/test_webapp_api_smoke.py tests/test_state_robustness.py`

### Phase 2: Runtime service decoupling
目标：将调度/执行队列逻辑从 HTTP handler 逻辑中抽离。

4. Commit D: Introduce run queue service
- New module `github_release_watcher/run_queue.py`
- Move enqueue/dequeue/task state model
- Keep existing API contract unchanged

5. Commit E: Introduce scheduler service
- New module `github_release_watcher/scheduler.py`
- Move repo interval recommendation and next-run logic

### Phase 3: Frontend modularization (no framework migration)
目标：将 `static/app.js` 拆分为职责模块，保留原生 JS。

6. Commit F: Extract API client and shared formatters
- `static/js/api-client.js`
- `static/js/formatters.js`

7. Commit G: Extract logs view renderer
- `static/js/logs-view.js`
- Move structured activity rendering / advanced details policy

8. Commit H: Extract repos and settings controllers
- `static/js/repos-controller.js`
- `static/js/settings-controller.js`

### Phase 4: Contract hardening and observability
目标：减少跨层隐式契约与回归盲区。

9. Commit I: Introduce API contract schema snapshot tests
- Add response shape regression tests for `/status`, `/config`, `/logs`, `/storage/*`

10. Commit J: Add runtime instrumentation hooks
- Add structured counters for queue depth, schedule lag, API latency (non-breaking)

## Guardrails
- No API endpoint removal or response field rename without explicit migration note.
- 每个 commit 保持可运行且可测试。
- 不在同一个 commit 混入“结构调整 + 行为改变”。
- 网络集成测试波动（rate limit）不得阻塞结构重构，可单独标记并保留本地可重复测试绿灯。

## Definition of Done
- `webapp.py` <= 1200 lines
- `static/app.js` <= 1200 lines
- `python3 -m pytest -q` stable pass (excluding optional network integration cases)
- 关键路径文档同步更新（README + this roadmap）
