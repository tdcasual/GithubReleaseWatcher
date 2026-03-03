# V2 Big-Bang Hard Cut Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在一次发布窗口内完成 V2 硬切，彻底删除 V1 运行时与兼容链路，只保留 `/api/v2` 与单一前端构建产物。

**Architecture:** 采用“先加守卫再删旧代码”的顺序：先建立全局防回退测试与 CI 门禁，再将 V2 API、鉴权、作业状态机、配置与存储能力补齐，最后一次性删除 V1 后端、V1 前端和双目录部署同步。运行时禁止读取 `state.json` 和 `/api/v1`，迁移只允许离线一次性导入脚本。坚持 DRY/YAGNI：每个任务只交付硬切必需功能。

**Tech Stack:** Python 3.12, FastAPI, SQLite, pytest, Node.js 20, TypeScript, Vite, Vitest, Vercel/Cloudflare edge proxy

**Skills:** @using-git-worktrees @test-driven-development @verification-before-completion @executing-plans

---

## Preconditions

1. 在独立 worktree 执行（不要在主工作目录直接改）。
2. 新分支前缀必须是 `codex/`。
3. 本计划每个 Task 完成后都单独提交，禁止大包提交。

建议命令：

```bash
git worktree add .worktrees/codex-v2-hard-cut -b codex/v2-hard-cut
git -C .worktrees/codex-v2-hard-cut status
```

期望：`On branch codex/v2-hard-cut`，工作树干净（允许本地未跟踪运行态文件）。

### Task 1: Add Global Legacy Ban Guardrails

**Files:**
- Create: `tests/test_v2_global_guardrails.py`
- Modify: `.github/workflows/ci.yml`
- Test: `tests/test_v2_global_guardrails.py`

**Step 1: Write the failing test**

```python
from pathlib import Path


def test_repo_disallows_api_v1_and_window_grw_strings() -> None:
    roots = [Path("github_release_watcher"), Path("deploy"), Path("README.md")]
    banned = ["/api/v1", "window.GRW"]
    hits = []
    for root in roots:
        files = [root] if root.is_file() else [p for p in root.rglob("*") if p.is_file()]
        for file in files:
            text = file.read_text(encoding="utf-8", errors="ignore")
            for token in banned:
                if token in text:
                    hits.append((str(file), token))
    assert not hits
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest -q tests/test_v2_global_guardrails.py`
Expected: FAIL，包含 `/api/v1` 或 `window.GRW` 命中信息。

**Step 3: Write minimal implementation**

```yaml
# .github/workflows/ci.yml
- name: Block legacy runtime tokens
  run: |
    if rg -n '/api/v1|window\.GRW' github_release_watcher deploy README.md; then
      echo "Legacy token found"
      exit 1
    fi
```

**Step 4: Run test to verify it passes (scope-limited pass)**

Run: `python3 -m pytest -q tests/test_v2_guardrails.py`
Expected: PASS（旧 guardrail 保持通过）。

**Step 5: Commit**

```bash
git add tests/test_v2_global_guardrails.py .github/workflows/ci.yml
git commit -m "test(ci): add global guardrails for v2 hard cut"
```

### Task 2: Make CLI V2-Only Surface

**Files:**
- Create: `tests/test_v2_cli_only.py`
- Modify: `github_release_watcher/cli.py`
- Modify: `watcher.py`
- Test: `tests/test_v2_cli_only.py`

**Step 1: Write the failing test**

```python
from github_release_watcher import cli


def test_cli_rejects_legacy_web_flags() -> None:
    parser = cli._build_parser()
    ns = parser.parse_args(["--web"])
    assert False, f"legacy flag should not parse: {ns}"


def test_cli_runs_v2_web_mode() -> None:
    parser = cli._build_parser()
    args = parser.parse_args(["--web", "--web-host", "0.0.0.0", "--web-port", "9000"])
    assert args.web is True
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest -q tests/test_v2_cli_only.py`
Expected: FAIL，当前 `--web` 语义仍指向 V1。

**Step 3: Write minimal implementation**

```python
# github_release_watcher/cli.py
parser.add_argument("--web", action="store_true", help="Start V2 FastAPI server.")
# remove: --web-v2, --no-ui, --web-no-scheduler branches

if args.web:
    return _run_web_v2(host=str(args.web_host), port=int(args.web_port), log_level=str(args.log_level).upper())
```

```python
# watcher.py
from github_release_watcher.cli import main
if __name__ == "__main__":
    raise SystemExit(main())
```

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest -q tests/test_v2_cli_only.py tests/test_v2_cli.py`
Expected: PASS。

**Step 5: Commit**

```bash
git add tests/test_v2_cli_only.py github_release_watcher/cli.py watcher.py tests/test_v2_cli.py
git commit -m "refactor(cli): switch to v2-only web entry"
```

### Task 3: Split V2 API Into Routers

**Files:**
- Create: `github_release_watcher/v2/api/__init__.py`
- Create: `github_release_watcher/v2/api/auth.py`
- Create: `github_release_watcher/v2/api/jobs.py`
- Create: `github_release_watcher/v2/api/events.py`
- Modify: `github_release_watcher/v2/app.py`
- Create: `tests/test_v2_app_routers.py`
- Test: `tests/test_v2_app_routers.py`

**Step 1: Write the failing test**

```python
from github_release_watcher.v2.app import create_app


def test_v2_app_registers_router_modules() -> None:
    app = create_app()
    paths = {route.path for route in app.routes}
    assert "/api/v2/auth/login" in paths
    assert "/api/v2/jobs" in paths
    assert "/api/v2/events" in paths
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest -q tests/test_v2_app_routers.py`
Expected: FAIL（当前路由仍集中在 `app.py`）。

**Step 3: Write minimal implementation**

```python
# github_release_watcher/v2/api/jobs.py
from fastapi import APIRouter
router = APIRouter(prefix="/api/v2/jobs", tags=["jobs"])

@router.get("")
def list_jobs_route():
    return {"items": []}
```

```python
# github_release_watcher/v2/app.py
from .api.auth import router as auth_router
from .api.jobs import router as jobs_router
from .api.events import router as events_router

app.include_router(auth_router)
app.include_router(jobs_router)
app.include_router(events_router)
```

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest -q tests/test_v2_app_routers.py tests/test_v2_app_health.py`
Expected: PASS。

**Step 5: Commit**

```bash
git add github_release_watcher/v2/api github_release_watcher/v2/app.py tests/test_v2_app_routers.py
git commit -m "refactor(v2): split fastapi routes into api modules"
```

### Task 4: Harden V2 Auth (Hashed Password + DB Sessions)

**Files:**
- Create: `github_release_watcher/v2/repositories/session_repo.py`
- Modify: `github_release_watcher/v2/db.py`
- Modify: `github_release_watcher/v2/auth.py`
- Modify: `github_release_watcher/v2/api/auth.py`
- Create: `tests/test_v2_auth_security.py`
- Test: `tests/test_v2_auth_security.py`

**Step 1: Write the failing test**

```python
from github_release_watcher.v2.auth import hash_password, verify_password


def test_password_hash_roundtrip() -> None:
    digest = hash_password("pass123")
    assert digest != "pass123"
    assert verify_password("pass123", digest)


def test_login_requires_persisted_session(tmp_path) -> None:
    # 仅示意：登录后重建 service 仍能验证 cookie
    assert False
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest -q tests/test_v2_auth_security.py`
Expected: FAIL（函数/持久会话未实现）。

**Step 3: Write minimal implementation**

```python
# github_release_watcher/v2/auth.py
import hashlib, hmac, secrets

def hash_password(raw: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", raw.encode(), salt.encode(), 200_000).hex()
    return f"{salt}${digest}"


def verify_password(raw: str, stored: str) -> bool:
    salt, digest = stored.split("$", 1)
    check = hashlib.pbkdf2_hmac("sha256", raw.encode(), salt.encode(), 200_000).hex()
    return hmac.compare_digest(check, digest)
```

```sql
-- github_release_watcher/v2/db.py schema extension
CREATE TABLE IF NOT EXISTS sessions (
  token TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  created_at TEXT NOT NULL
);
```

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest -q tests/test_v2_auth_security.py tests/test_v2_auth.py`
Expected: PASS。

**Step 5: Commit**

```bash
git add github_release_watcher/v2/db.py github_release_watcher/v2/auth.py github_release_watcher/v2/api/auth.py github_release_watcher/v2/repositories/session_repo.py tests/test_v2_auth_security.py
git commit -m "feat(v2-auth): add hashed password and sqlite-backed sessions"
```

### Task 5: Implement Job State Machine + Worker

**Files:**
- Create: `github_release_watcher/v2/application/jobs_service.py`
- Create: `github_release_watcher/v2/repositories/jobs_repo.py`
- Create: `github_release_watcher/v2/worker.py`
- Modify: `github_release_watcher/v2/jobs.py`
- Modify: `github_release_watcher/v2/api/jobs.py`
- Modify: `github_release_watcher/v2/api/events.py`
- Create: `tests/test_v2_jobs_lifecycle.py`
- Test: `tests/test_v2_jobs_lifecycle.py`

**Step 1: Write the failing test**

```python
def test_job_status_flow_transitions(client):
    job = client.post("/api/v2/jobs", json={"kind": "run_repos", "payload": {"repos": ["o/r"]}}).json()
    job_id = job["id"]
    # worker tick
    client.post(f"/api/v2/jobs/{job_id}/events", json={"event_type": "started", "payload": {}})
    client.post(f"/api/v2/jobs/{job_id}/events", json={"event_type": "succeeded", "payload": {}})
    items = client.get("/api/v2/jobs").json()["items"]
    target = [x for x in items if x["id"] == job_id][0]
    assert target["status"] == "succeeded"
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest -q tests/test_v2_jobs_lifecycle.py`
Expected: FAIL（状态迁移未串联）。

**Step 3: Write minimal implementation**

```python
# github_release_watcher/v2/application/jobs_service.py
ALLOWED = {
    "queued": {"running", "canceled"},
    "running": {"succeeded", "failed", "canceled"},
    "succeeded": set(),
    "failed": set(),
    "canceled": set(),
}

def transition(current: str, nxt: str) -> str:
    if nxt not in ALLOWED.get(current, set()):
        raise ValueError(f"invalid transition: {current}->{nxt}")
    return nxt
```

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest -q tests/test_v2_jobs_lifecycle.py tests/test_v2_jobs_api.py tests/test_v2_events_api.py`
Expected: PASS。

**Step 5: Commit**

```bash
git add github_release_watcher/v2/application/jobs_service.py github_release_watcher/v2/repositories/jobs_repo.py github_release_watcher/v2/worker.py github_release_watcher/v2/jobs.py github_release_watcher/v2/api/jobs.py github_release_watcher/v2/api/events.py tests/test_v2_jobs_lifecycle.py
git commit -m "feat(v2-jobs): add state machine and worker lifecycle"
```

### Task 6: Add Repos/Settings/Storage V2 APIs (SQLite-Backed)

**Files:**
- Create: `github_release_watcher/v2/api/repos.py`
- Create: `github_release_watcher/v2/api/settings.py`
- Create: `github_release_watcher/v2/api/storage.py`
- Create: `github_release_watcher/v2/repositories/repos_repo.py`
- Create: `github_release_watcher/v2/repositories/settings_repo.py`
- Modify: `github_release_watcher/v2/db.py`
- Modify: `github_release_watcher/v2/app.py`
- Create: `tests/test_v2_repos_settings_storage_api.py`
- Test: `tests/test_v2_repos_settings_storage_api.py`

**Step 1: Write the failing test**

```python
def test_v2_settings_and_repos_roundtrip(client):
    put = client.put("/api/v2/settings", json={"scheduler": {"enabled": True}})
    assert put.status_code == 200
    post_repo = client.post("/api/v2/repos", json={"key": "owner/repo", "enabled": True})
    assert post_repo.status_code == 201
    listing = client.get("/api/v2/repos").json()["items"]
    assert any(item["key"] == "owner/repo" for item in listing)
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest -q tests/test_v2_repos_settings_storage_api.py`
Expected: FAIL（路由未实现）。

**Step 3: Write minimal implementation**

```python
# github_release_watcher/v2/api/repos.py
from fastapi import APIRouter
router = APIRouter(prefix="/api/v2/repos", tags=["repos"])

@router.get("")
def list_repos():
    return {"items": []}

@router.post("", status_code=201)
def create_repo(body: dict):
    return body
```

```python
# github_release_watcher/v2/db.py schema extension
CREATE TABLE IF NOT EXISTS app_settings (
  key TEXT PRIMARY KEY,
  value_json TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
```

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest -q tests/test_v2_repos_settings_storage_api.py`
Expected: PASS。

**Step 5: Commit**

```bash
git add github_release_watcher/v2/api/repos.py github_release_watcher/v2/api/settings.py github_release_watcher/v2/api/storage.py github_release_watcher/v2/repositories/repos_repo.py github_release_watcher/v2/repositories/settings_repo.py github_release_watcher/v2/db.py github_release_watcher/v2/app.py tests/test_v2_repos_settings_storage_api.py
git commit -m "feat(v2-api): add repos settings storage endpoints"
```

### Task 7: Implement One-Time Offline Importer (V1 -> V2)

**Files:**
- Create: `scripts/migrate_v1_to_v2.py`
- Create: `tests/test_v2_offline_import.py`
- Modify: `README.md`
- Test: `tests/test_v2_offline_import.py`

**Step 1: Write the failing test**

```python
from pathlib import Path
from scripts.migrate_v1_to_v2 import run_import


def test_offline_import_generates_report(tmp_path: Path) -> None:
    cfg = tmp_path / "config.toml"
    state = tmp_path / "state.json"
    db = tmp_path / "v2.sqlite3"
    report = tmp_path / "report.json"
    cfg.write_text('[[repos]]\nname="owner/repo"\n', encoding="utf-8")
    state.write_text('{"version":2,"repos":{"owner/repo":{"releases":{}}}}', encoding="utf-8")
    run_import(config_path=cfg, state_path=state, db_path=db, report_path=report)
    assert report.exists()
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest -q tests/test_v2_offline_import.py`
Expected: FAIL（脚本不存在）。

**Step 3: Write minimal implementation**

```python
# scripts/migrate_v1_to_v2.py
import json

def run_import(*, config_path, state_path, db_path, report_path):
    # 只做一次性离线导入，不在运行时调用
    summary = {"repos": 0, "releases": 0, "assets": 0}
    report_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
```

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest -q tests/test_v2_offline_import.py`
Expected: PASS。

**Step 5: Commit**

```bash
git add scripts/migrate_v1_to_v2.py tests/test_v2_offline_import.py README.md
git commit -m "feat(migration): add one-time offline v1-to-v2 importer"
```

### Task 8: Create Frontend TypeScript App (Single Source)

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/src/main.ts`
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/api/client.test.ts`
- Create: `frontend/src/pages/App.tsx`
- Delete: `github_release_watcher/static/*`
- Test: `frontend/src/api/client.test.ts`

**Step 1: Write the failing test**

```ts
import { describe, it, expect } from "vitest";
import { buildApiPath } from "./client";

describe("client", () => {
  it("uses /api/v2 prefix", () => {
    expect(buildApiPath("/jobs")).toBe("/api/v2/jobs");
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- --run`
Expected: FAIL（项目/函数未创建）。

**Step 3: Write minimal implementation**

```ts
// frontend/src/api/client.ts
export function buildApiPath(path: string): string {
  return `/api/v2${path}`;
}
```

```json
// frontend/package.json
{
  "name": "grw-frontend",
  "private": true,
  "scripts": {
    "build": "vite build",
    "test": "vitest"
  },
  "devDependencies": {
    "typescript": "^5.6.0",
    "vite": "^5.4.0",
    "vitest": "^2.1.0"
  }
}
```

**Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- --run`
Expected: PASS。

**Step 5: Commit**

```bash
git add frontend
git rm -r github_release_watcher/static
git commit -m "feat(frontend): migrate to typescript single-source app"
```

### Task 9: Switch Deploy Proxies to V2 and Remove V1 Endpoint

**Files:**
- Create: `deploy/vercel/api/v2/[...path].js`
- Delete: `deploy/vercel/api/v1/[...path].js`
- Modify: `deploy/cloudflare-worker/src/index.js`
- Create: `tests/test_v2_deploy_proxy.py`
- Test: `tests/test_v2_deploy_proxy.py`

**Step 1: Write the failing test**

```python
from pathlib import Path


def test_vercel_proxy_targets_v2_only() -> None:
    proxy = Path("deploy/vercel/api/v2/[...path].js").read_text(encoding="utf-8")
    assert "/api/v2" in proxy
    assert "/api/v1" not in proxy
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest -q tests/test_v2_deploy_proxy.py`
Expected: FAIL（v2 代理文件尚未创建）。

**Step 3: Write minimal implementation**

```js
// deploy/vercel/api/v2/[...path].js
upstreamUrl.pathname = `${upstreamUrl.pathname.replace(/\/$/, "")}/api/v2${restPath}`;
```

```js
// deploy/cloudflare-worker/src/index.js
if (incomingUrl.pathname.startsWith("/api/v1")) {
  return new Response("Not Found", { status: 404 });
}
```

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest -q tests/test_v2_deploy_proxy.py`
Expected: PASS。

**Step 5: Commit**

```bash
git add deploy/vercel/api/v2/'[...path].js' deploy/cloudflare-worker/src/index.js tests/test_v2_deploy_proxy.py
git rm deploy/vercel/api/v1/'[...path].js'
git commit -m "refactor(deploy): route proxies to api v2 only"
```

### Task 10: Delete Legacy Python Runtime and Legacy Tests

**Files:**
- Delete: `github_release_watcher/webapp.py`
- Delete: `github_release_watcher/webapp_api_router.py`
- Delete: `github_release_watcher/watcher.py`
- Delete: `github_release_watcher/auth_service.py`
- Delete: `github_release_watcher/run_queue.py`
- Delete: `github_release_watcher/scheduler.py`
- Delete: `github_release_watcher/settings_service.py`
- Delete: `github_release_watcher/repo_query_service.py`
- Delete: `github_release_watcher/storage_health_service.py`
- Delete: `github_release_watcher/webapp_handler_utils.py`
- Delete: `github_release_watcher/webapp_overrides.py`
- Delete: `github_release_watcher/webapp_payloads.py`
- Delete: `github_release_watcher/state.py`
- Delete: `github_release_watcher/state_migrations.py`
- Delete: `tests/test_webapp_api_smoke.py`
- Delete: `tests/test_webapp_api_contract.py`
- Delete: `tests/test_webapp_end_to_end_minimal.py`
- Delete: `tests/test_run_queue.py`
- Delete: `tests/test_repo_query_service.py`
- Create: `tests/test_no_legacy_runtime.py`
- Test: `tests/test_no_legacy_runtime.py`

**Step 1: Write the failing test**

```python
from pathlib import Path


def test_legacy_runtime_files_removed() -> None:
    legacy = [
        "github_release_watcher/webapp.py",
        "github_release_watcher/watcher.py",
        "github_release_watcher/webapp_api_router.py",
    ]
    still_exists = [p for p in legacy if Path(p).exists()]
    assert not still_exists
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest -q tests/test_no_legacy_runtime.py`
Expected: FAIL（文件仍存在）。

**Step 3: Write minimal implementation**

```bash
git rm github_release_watcher/webapp.py github_release_watcher/webapp_api_router.py github_release_watcher/watcher.py
git rm github_release_watcher/auth_service.py github_release_watcher/run_queue.py github_release_watcher/scheduler.py
git rm github_release_watcher/settings_service.py github_release_watcher/repo_query_service.py github_release_watcher/storage_health_service.py
git rm github_release_watcher/webapp_handler_utils.py github_release_watcher/webapp_overrides.py github_release_watcher/webapp_payloads.py
git rm github_release_watcher/state.py github_release_watcher/state_migrations.py
```

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest -q tests/test_no_legacy_runtime.py`
Expected: PASS。

**Step 5: Commit**

```bash
git add tests/test_no_legacy_runtime.py
git rm tests/test_webapp_api_smoke.py tests/test_webapp_api_contract.py tests/test_webapp_end_to_end_minimal.py tests/test_run_queue.py tests/test_repo_query_service.py
git commit -m "refactor(core): remove legacy v1 runtime and tests"
```

### Task 11: Remove Duplicate Distribution Flow and Finalize Packaging

**Files:**
- Delete: `scripts/release/sync_vercel_public.sh`
- Delete: `deploy/vercel/public/*` (改为前端构建产物输出目录)
- Modify: `pyproject.toml`
- Create: `tests/test_v2_distribution_layout.py`
- Test: `tests/test_v2_distribution_layout.py`

**Step 1: Write the failing test**

```python
from pathlib import Path


def test_no_manual_static_sync_script() -> None:
    assert not Path("scripts/release/sync_vercel_public.sh").exists()


def test_vercel_public_contains_build_marker() -> None:
    assert Path("deploy/vercel/public/.generated-by-frontend-build").exists()
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest -q tests/test_v2_distribution_layout.py`
Expected: FAIL（旧脚本仍在、marker 不存在）。

**Step 3: Write minimal implementation**

```bash
git rm scripts/release/sync_vercel_public.sh
git rm -r deploy/vercel/public
touch deploy/vercel/public/.generated-by-frontend-build
```

```toml
# pyproject.toml
[tool.setuptools.package-data]
github_release_watcher = []
```

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest -q tests/test_v2_distribution_layout.py`
Expected: PASS。

**Step 5: Commit**

```bash
git add pyproject.toml tests/test_v2_distribution_layout.py deploy/vercel/public/.generated-by-frontend-build
git commit -m "chore(dist): remove duplicated static sync pipeline"
```

### Task 12: Rewrite Docs and Run Full Verification Gate

**Files:**
- Modify: `README.md`
- Modify: `docs/plans/2026-03-03-v2-breaking-clean-design.md`
- Modify: `.github/workflows/ci.yml`
- Test: `tests/test_v2_global_guardrails.py`

**Step 1: Write the failing test**

```python
from pathlib import Path


def test_readme_is_v2_only() -> None:
    text = Path("README.md").read_text(encoding="utf-8")
    assert "/api/v1" not in text
    assert "python3 watcher.py --web" in text
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest -q tests/test_v2_global_guardrails.py::test_repo_disallows_api_v1_and_window_grw_strings`
Expected: FAIL（文档仍有 v1 描述）。

**Step 3: Write minimal implementation**

```markdown
# README.md
- 删除全部 `/api/v1/*` 接口说明
- 启动方式仅保留 `python3 watcher.py --web --web-host 127.0.0.1 --web-port 8000`（语义=V2）
- 增加“离线导入一次性工具”章节
```

**Step 4: Run test to verify it passes + full gate**

Run: `python3 -m pytest -q`
Expected: PASS。

Run: `cd frontend && npm ci && npm run test -- --run && npm run build`
Expected: PASS。

Run: `for f in deploy/vercel/api/v2/*.js deploy/cloudflare-worker/src/*.js; do node --check "$f"; done`
Expected: PASS。

Run: `rg -n '/api/v1|window\.GRW' github_release_watcher deploy README.md`
Expected: 无输出。

**Step 5: Commit**

```bash
git add README.md docs/plans/2026-03-03-v2-breaking-clean-design.md .github/workflows/ci.yml tests/test_v2_global_guardrails.py
git commit -m "docs(ci): finalize v2-only hard cut docs and verification gate"
```

---

## Final Verification Checklist (Release Gate)

1. `python3 -m pytest -q` 全绿。
2. `cd frontend && npm run test -- --run && npm run build` 全绿。
3. `rg -n '/api/v1|window\.GRW' github_release_watcher deploy README.md` 无输出。
4. 仓库内不再存在以下路径：
   - `github_release_watcher/webapp.py`
   - `github_release_watcher/watcher.py`
   - `github_release_watcher/static/`
   - `deploy/vercel/api/v1/[...path].js`
   - `scripts/release/sync_vercel_public.sh`

## Notes

- 本计划是破坏式硬切，绝不保留线上兼容层。
- 导入工具是一次性离线用途，运行时严格禁止读取 V1 数据格式。
- 若任一步骤引入兼容字段或 V1 token，必须回退并重做。
