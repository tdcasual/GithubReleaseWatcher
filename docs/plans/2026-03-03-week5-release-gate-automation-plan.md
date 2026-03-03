# Week5 Release Gate Automation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 Gate 4（自动化回归）纳入现有验收工具链（Gate2/3 报告、清单同步、状态检查），形成可重复、可追溯的发布门禁流水。

**Architecture:** 新增 `new_gate4_report.sh` 负责执行回归命令并产出 `gate4-report.md`，再把该报告接入 `new_acceptance_packet.sh`、`sync_acceptance_gates.sh` 与 `check_acceptance_status.sh`。通过 shell + Python 测试保障 PASS/BLOCKED 语义一致。

**Tech Stack:** bash, Python 3.12, unittest/pytest.

---

### Task 1: Gate4 报告脚本（可执行 + 可测试）

**Files:**
- Create: `scripts/qa/new_gate4_report.sh`
- Create: `tests/test_acceptance_gate4_report.py`

**Step 1: Write failing tests**

- 新增测试覆盖：
  - 脚本可生成 `gate4-report.md` 且 PASS/BLOCKED 勾选正确。
  - 支持 `--strict` 时在 BLOCKED 返回 2。
  - 支持 `--commands-file` 注入轻量命令，便于本地/测试快速执行。

**Step 2: Run tests to verify RED**

Run: `python3 -m pytest -q tests/test_acceptance_gate4_report.py`
Expected: fail because script does not exist.

**Step 3: Write minimal implementation**

- 实现 `new_gate4_report.sh`：
  - 输入：`[RUN_DIR] [--strict] [--commands-file FILE]`
  - 输出：`$RUN_DIR/gate4-report.md` + `$RUN_DIR/gate4-logs/*.log`
  - 默认命令集：
    1. `bash scripts/release/sync_vercel_public.sh`
    2. `python3 -m pytest -q -k "not download_integration"`
    3. `for action in github_release_watcher/static/*.js deploy/vercel/public/*.js; do node --check "$action"; done`
    4. `bash scripts/qa/smoke_api_flow.sh`
  - 结果规则：全部成功 => Gate4 pass，否则 blocked。

**Step 4: Run tests to verify GREEN**

Run: `python3 -m pytest -q tests/test_acceptance_gate4_report.py`
Expected: pass.

### Task 2: 接入 Gate 工具链

**Files:**
- Modify: `scripts/qa/new_acceptance_packet.sh`
- Modify: `scripts/qa/sync_acceptance_gates.sh`
- Modify: `scripts/qa/check_acceptance_status.sh`
- Modify: `tests/test_acceptance_gate_sync.py`
- Create: `tests/test_acceptance_status_checker.py`

**Step 1: Write failing tests**

- 增加/新增测试验证：
  - `sync_acceptance_gates.sh` 能同步 Gate4 勾选状态。
  - `check_acceptance_status.sh` 在存在 Gate4 报告且非 PASS 时给出阻塞原因。

**Step 2: Run tests to verify RED**

Run: `python3 -m pytest -q tests/test_acceptance_gate_sync.py tests/test_acceptance_status_checker.py`
Expected: fail before script updates.

**Step 3: Write minimal implementation**

- `new_acceptance_packet.sh` 自动生成/引用 `gate4-report.md`。
- `sync_acceptance_gates.sh` 从 `gate4-report.md` 同步 Gate4 勾选。
- `check_acceptance_status.sh` 额外输出 Gate4 报告状态，并在非 PASS 时阻塞。

**Step 4: Run tests to verify GREEN**

Run: `python3 -m pytest -q tests/test_acceptance_gate_sync.py tests/test_acceptance_status_checker.py`
Expected: pass.

### Task 3: 文档与最终验证

**Files:**
- Modify: `README.md`
- Modify: `docs/plans/2026-03-01-release-acceptance-checklist.md`

**Step 1: Update docs**

- README 新增 `scripts/qa/new_gate4_report.sh` 说明。
- 验收清单第 7 节补充 Gate4 自动报告产出路径与使用方式。

**Step 2: Run full verification**

Run: `python3 -m pytest -q tests/test_acceptance_gate4_report.py tests/test_acceptance_gate_sync.py tests/test_acceptance_status_checker.py`
Run: `python3 -m pytest -q -k "not download_integration"`
Run: `for action in github_release_watcher/static/*.js deploy/vercel/public/*.js; do node --check "$action"; done`
Expected: all pass.
