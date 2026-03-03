# Technical Debt Paydown (2-Week) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在 2 周内把当前“可运行但演进成本高”的状态，收敛到“结构可维护、部署一致、回归可追踪”的状态，并把高风险历史包袱清零到可控水平。

**Architecture:** 优先处理高杠杆债务：先打通部署一致性（单一前端来源），再拆后端入口单体（`webapp.py`），同时补上 API 契约测试与运行时指标。全程保持“不改现有对外行为”的重构策略，避免功能回归。

**Tech Stack:** Python 3.12, `unittest`/`pytest`, 原生 JS 前端, `http.server` 内置 Web 服务, Vercel/Cloudflare 代理部署, GitHub Actions（新增）。

---

## Sprint Scope (2 Weeks)

### In Scope

1. 统一前端发布源，消除 `github_release_watcher/static` 与 `deploy/vercel/public` 的分叉。
2. 把 `webapp.py` API 分发和设置写入逻辑再拆分两层，降低复杂度。
3. 增加 API 响应结构快照测试（契约测试）。
4. 增加队列/调度/API 基础运行时指标（非侵入）。
5. 补充 CI 自动回归。

### Out of Scope

1. 前端框架迁移（例如 React/Vue）。
2. 存储后端重写（例如 S3/对象存储抽象）。
3. OAuth/SSO 认证体系替换。

---

## Week 1 Milestones

### Task 1: Frontend Single Source of Truth

**Files:**
- Create: `scripts/release/sync_vercel_public.sh`
- Modify: `deploy/vercel/public/index.html`
- Modify: `deploy/vercel/public/app.js`
- Modify: `deploy/vercel/public/styles.css`
- Modify: `deploy/vercel/public/repo.js`
- Modify: `deploy/vercel/public/repo.html`
- Modify: `README.md`
- Test: `tests/test_vercel_static_sync.py`

**Step 1: Write the failing test**

```python
import hashlib
from pathlib import Path

FILES = ["index.html", "app.js", "styles.css", "repo.js", "repo.html", "favicon.svg"]

def sha1(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()

def test_vercel_public_is_synced_from_static():
    root = Path(__file__).resolve().parents[1]
    for name in FILES:
        src = root / "github_release_watcher" / "static" / name
        dst = root / "deploy" / "vercel" / "public" / name
        assert sha1(src) == sha1(dst), f"{name} is not synced"
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest -q tests/test_vercel_static_sync.py`
Expected: FAIL with at least one `is not synced`.

**Step 3: Write minimal implementation**

```bash
#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SRC="$ROOT/github_release_watcher/static"
DST="$ROOT/deploy/vercel/public"
for f in index.html app.js styles.css repo.js repo.html favicon.svg; do
  cp "$SRC/$f" "$DST/$f"
done
```

**Step 4: Run test to verify it passes**

Run: `bash scripts/release/sync_vercel_public.sh && python3 -m pytest -q tests/test_vercel_static_sync.py`
Expected: PASS.

**Step 5: Commit**

```bash
git add scripts/release/sync_vercel_public.sh tests/test_vercel_static_sync.py deploy/vercel/public README.md
git commit -m "chore(release): enforce vercel static sync from canonical frontend source"
```

---

### Task 2: Extract API Router From `webapp.py`

**Files:**
- Create: `github_release_watcher/webapp_api_router.py`
- Modify: `github_release_watcher/webapp.py`
- Test: `tests/test_webapp_api_smoke.py`
- Test: `tests/test_webapp_api_contract.py`

**Step 1: Write the failing test**

```python
from pathlib import Path

def test_webapp_handler_delegates_to_router_module():
    source = Path("github_release_watcher/webapp.py").read_text(encoding="utf-8")
    assert "from .webapp_api_router import handle_api_request" in source
    assert "handle_api_request(" in source
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest -q tests/test_webapp_api_contract.py::test_webapp_handler_delegates_to_router_module`
Expected: FAIL.

**Step 3: Write minimal implementation**

```python
# webapp_api_router.py
def handle_api_request(handler, path, split):
    # move existing branch logic from Handler._handle_api here
    ...
```

```python
# webapp.py
from .webapp_api_router import handle_api_request
...
def _handle_api(self, path, split) -> None:
    handle_api_request(self, path, split)
```

**Step 4: Run tests to verify pass**

Run: `python3 -m pytest -q tests/test_webapp_api_smoke.py tests/test_webapp_api_contract.py`
Expected: PASS.

**Step 5: Commit**

```bash
git add github_release_watcher/webapp_api_router.py github_release_watcher/webapp.py tests/test_webapp_api_contract.py tests/test_webapp_api_smoke.py
git commit -m "refactor(web): extract API routing from webapp handler"
```

---

### Task 3: Extract Settings Update Service

**Files:**
- Create: `github_release_watcher/settings_service.py`
- Modify: `github_release_watcher/webapp.py`
- Test: `tests/test_settings_service.py`
- Test: `tests/test_webapp_api_smoke.py`

**Step 1: Write the failing test**

```python
from github_release_watcher.settings_service import SettingsService

def test_settings_service_rejects_webdav_without_base_url():
    svc = SettingsService()
    payload = {"storage": {"mode": "webdav", "webdav": {"base_url": ""}}}
    try:
        svc.validate(payload)
    except ValueError as exc:
        assert "base_url" in str(exc)
    else:
        assert False, "expected ValueError"
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest -q tests/test_settings_service.py::test_settings_service_rejects_webdav_without_base_url`
Expected: FAIL (module not found / missing class).

**Step 3: Write minimal implementation**

```python
class SettingsService:
    def validate(self, payload: dict) -> None:
        storage = payload.get("storage", {})
        mode = str(storage.get("mode") or "local").lower()
        if mode == "webdav":
            webdav = storage.get("webdav", {})
            if not str(webdav.get("base_url") or "").strip():
                raise ValueError("webdav.base_url is required when storage.mode = 'webdav'")
```

**Step 4: Run tests to verify pass**

Run: `python3 -m pytest -q tests/test_settings_service.py tests/test_webapp_api_smoke.py`
Expected: PASS.

**Step 5: Commit**

```bash
git add github_release_watcher/settings_service.py github_release_watcher/webapp.py tests/test_settings_service.py tests/test_webapp_api_smoke.py
git commit -m "refactor(web): extract settings validation/update service"
```

---

### Task 4: API Contract Snapshot Tests

**Files:**
- Create: `tests/test_webapp_api_contract.py`
- Create: `tests/snapshots/status_shape.json`
- Create: `tests/snapshots/config_shape.json`
- Create: `tests/snapshots/logs_shape.json`
- Modify: `tests/test_webapp_api_smoke.py`

**Step 1: Write the failing test**

```python
def test_status_response_shape_snapshot():
    payload = get_status_payload_somehow()
    assert sorted(payload.keys()) == sorted(["started_at", "config_path", "scheduler", "run", "config"])
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest -q tests/test_webapp_api_contract.py::test_status_response_shape_snapshot`
Expected: FAIL.

**Step 3: Write minimal implementation**

```python
def normalize_shape(obj):
    if isinstance(obj, dict):
        return {k: normalize_shape(v) for k, v in sorted(obj.items())}
    if isinstance(obj, list):
        return [normalize_shape(v) for v in obj[:3]]
    return type(obj).__name__
```

**Step 4: Run tests to verify pass**

Run: `python3 -m pytest -q tests/test_webapp_api_contract.py tests/test_webapp_api_smoke.py`
Expected: PASS.

**Step 5: Commit**

```bash
git add tests/test_webapp_api_contract.py tests/snapshots tests/test_webapp_api_smoke.py
git commit -m "test(api): add response shape contract snapshots for key endpoints"
```

---

## Week 2 Milestones

### Task 5: Runtime Instrumentation Hooks

**Files:**
- Create: `github_release_watcher/metrics.py`
- Modify: `github_release_watcher/run_queue.py`
- Modify: `github_release_watcher/scheduler.py`
- Modify: `github_release_watcher/webapp.py`
- Test: `tests/test_runtime_metrics.py`

**Step 1: Write the failing test**

```python
def test_snapshot_exposes_runtime_metrics():
    snap = app.snapshot()
    assert "metrics" in snap
    assert "api_request_total" in snap["metrics"]
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest -q tests/test_runtime_metrics.py::test_snapshot_exposes_runtime_metrics`
Expected: FAIL.

**Step 3: Write minimal implementation**

```python
class MetricsRegistry:
    def __init__(self):
        self.api_request_total = 0
        self.queue_enqueue_total = 0
        self.queue_rejected_total = 0
        self.scheduler_lag_seconds = 0.0
```

**Step 4: Run tests to verify pass**

Run: `python3 -m pytest -q tests/test_runtime_metrics.py tests/test_run_queue.py tests/test_scheduler_service.py`
Expected: PASS.

**Step 5: Commit**

```bash
git add github_release_watcher/metrics.py github_release_watcher/run_queue.py github_release_watcher/scheduler.py github_release_watcher/webapp.py tests/test_runtime_metrics.py
git commit -m "feat(observability): add runtime metrics for queue scheduler and api"
```

---

### Task 6: Repo Page Deduplicate Shared Client Helpers

**Files:**
- Modify: `github_release_watcher/static/repo.js`
- Modify: `github_release_watcher/static/api-client.js`
- Modify: `github_release_watcher/static/formatters.js`
- Test: `tests/test_repo_page_shared_modules.py`

**Step 1: Write the failing test**

```python
from pathlib import Path

def test_repo_js_uses_shared_api_client():
    repo_js = Path("github_release_watcher/static/repo.js").read_text(encoding="utf-8")
    assert "window.GRWApiClient?.API" in repo_js
    assert "const API = {" not in repo_js
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest -q tests/test_repo_page_shared_modules.py`
Expected: FAIL.

**Step 3: Write minimal implementation**

```javascript
const API = window.GRWApiClient?.API;
if (!API) throw new Error("Shared API client not loaded");
```

**Step 4: Run tests to verify pass**

Run: `python3 -m pytest -q tests/test_repo_page_shared_modules.py tests/test_ui_mobile_accessibility.py`
Expected: PASS.

**Step 5: Commit**

```bash
git add github_release_watcher/static/repo.js github_release_watcher/static/api-client.js github_release_watcher/static/formatters.js tests/test_repo_page_shared_modules.py
git commit -m "refactor(ui): reuse shared api/formatter modules in repo page"
```

---

### Task 7: Config Strictness Guard (Warn Unknown Keys)

**Files:**
- Modify: `github_release_watcher/config.py`
- Test: `tests/test_config_unknown_keys.py`
- Modify: `README.md`

**Step 1: Write the failing test**

```python
def test_load_config_warns_unknown_top_level_keys(caplog):
    cfg = load_config(path_with_unknown_key)
    assert "unknown config key" in caplog.text.lower()
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest -q tests/test_config_unknown_keys.py`
Expected: FAIL.

**Step 3: Write minimal implementation**

```python
KNOWN_TOP = {"interval_seconds", "download_dir", "state_file", "keep_last", "github", "storage", "repos"}
for key in data.keys():
    if key not in KNOWN_TOP:
        logging.warning("Unknown config key ignored: %s", key)
```

**Step 4: Run tests to verify pass**

Run: `python3 -m pytest -q tests/test_config_unknown_keys.py tests/test_webdav_reliability.py`
Expected: PASS.

**Step 5: Commit**

```bash
git add github_release_watcher/config.py tests/test_config_unknown_keys.py README.md
git commit -m "chore(config): warn on unknown config keys to reduce silent misconfiguration"
```

---

### Task 8: Add CI Workflow

**Files:**
- Create: `.github/workflows/ci.yml`
- Modify: `README.md`

**Step 1: Write the failing test**

```python
from pathlib import Path

def test_ci_workflow_exists():
    assert Path(".github/workflows/ci.yml").exists()
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest -q tests/test_ci_presence.py`
Expected: FAIL.

**Step 3: Write minimal implementation**

```yaml
name: ci
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -e .
      - run: python3 -m pytest -q
      - run: node --check github_release_watcher/static/app.js
      - run: node --check github_release_watcher/static/repo.js
```

**Step 4: Run test to verify pass**

Run: `python3 -m pytest -q tests/test_ci_presence.py`
Expected: PASS.

**Step 5: Commit**

```bash
git add .github/workflows/ci.yml tests/test_ci_presence.py README.md
git commit -m "chore(ci): add baseline regression workflow for python and frontend syntax checks"
```

---

## Daily Schedule (Recommended)

1. Day 1: Task 1 + Task 2 (part 1).
2. Day 2: Task 2 (finish) + Task 3.
3. Day 3: Task 4.
4. Day 4: 回归修复与文档同步。
5. Day 5: Week 1 回归冻结（仅修 bug）。
6. Day 6: Task 5。
7. Day 7: Task 6。
8. Day 8: Task 7。
9. Day 9: Task 8 + 端到端回归。
10. Day 10: 发布候选分支验证 + 风险收口。

---

## Acceptance Criteria

1. `github_release_watcher/webapp.py` 行数降到 `<= 1200`。
2. `github_release_watcher/static/app.js` 行数降到 `<= 1200`。
3. `deploy/vercel/public/*` 与 `github_release_watcher/static/*` 核心页面文件一致（哈希相同）。
4. `python3 -m pytest -q` 全绿。
5. `node --check github_release_watcher/static/app.js` 与 `repo.js` 全绿。
6. 新增 API 契约测试稳定通过。
7. `snapshot().metrics` 可返回最小指标集合（API 请求计数、队列拒绝数、调度滞后）。

---

## Rollback Strategy

1. 每个任务单独 commit，禁止“多任务混提”。
2. 若契约测试失败，优先回滚最近一个 refactor commit，不回滚已验证的部署同步与测试资产。
3. 发布前保留 `state.json`、`config.override.json`、下载目录，不做数据删除。

---

## Command Checklist (End of Sprint)

1. `bash scripts/release/sync_vercel_public.sh`
2. `python3 -m pytest -q`
3. `node --check github_release_watcher/static/app.js`
4. `node --check github_release_watcher/static/repo.js`
5. `node --check deploy/vercel/public/app.js`
6. `node --check deploy/vercel/public/repo.js`

Plan complete and saved to `docs/plans/2026-03-03-technical-debt-paydown-plan.md`. Two execution options:

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

**Which approach?**
