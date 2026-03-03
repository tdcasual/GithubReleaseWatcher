# 2026-03-03 V2 Long-Term Debt Route (8 Tasks)

## Goal
在不考虑兼容性的前提下，完成长期清债路线的剩余工作：安全基线、分层解耦、可观测存储健康、CI 防回退与发布收口。

## Task 1: Re-verify completed baseline debt tasks
- Verify scripts/docs/guardrails/importer/API 4xx current status.
- Commands:
  - `python3 -m pytest -q tests/test_v2_global_guardrails.py tests/test_v2_offline_import.py tests/test_v2_jobs_api.py tests/test_v2_repos_settings_storage_api.py`
  - `bash scripts/qa/new_gate4_report.sh "$(mktemp -d)" --strict`

## Task 2: Remove insecure default auth bootstrap
- Remove `admin/admin` style implicit defaults from runtime startup.
- Require explicit `--auth-username` and `--auth-password` or env fallback with non-empty checks.
- Update CLI tests and QA bootstrap scripts accordingly.

## Task 3: Harden session cookie security contract
- Set secure cookie defaults (`Secure`, `HttpOnly`, `SameSite=Lax`) with explicit local override flag.
- Add tests asserting secure cookie behavior.

## Task 4: Split jobs into layered modules (application/domain/repository)
- Extract state machine and transition validation to domain module.
- Extract persistence operations to repositories module.
- Keep API contract unchanged.

## Task 5: Replace static storage health response with service/provider
- Introduce storage health service reading persisted settings and provider output.
- Return non-static shape with timestamp and source fields.
- Add tests for local/webdav modes and missing settings.

## Task 6: Expand anti-regression guardrails
- Extend global token guard to docs plans + scripts + deploy and removed module imports.
- Add tests for banned legacy tokens and removed module references.

## Task 7: Tighten migration/import verification
- Ensure importer writes repos/settings/job/events and includes deterministic report fields.
- Add tests for invalid repo keys and settings import flag.

## Task 8: Final verification and branch finish
- Full verification:
  - `python3 -m pytest -q`
  - `npm --prefix frontend test`
  - `npm --prefix frontend run build`
  - `bash scripts/qa/new_gate4_report.sh "$(mktemp -d)" --strict`
- Use finishing workflow to merge/push/cleanup.
