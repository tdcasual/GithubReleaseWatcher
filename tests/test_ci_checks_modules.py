from __future__ import annotations

from pathlib import Path


def _ci_text() -> str:
    return Path(".github/workflows/ci.yml").read_text(encoding="utf-8")


def test_ci_checks_all_static_js_modules() -> None:
    ci = _ci_text()
    assert "github_release_watcher/static/*.js" in ci
    assert "deploy/vercel/public/*.js" in ci
    assert "node --check" in ci


def test_ci_blocks_local_artifacts_from_tracking() -> None:
    ci = _ci_text()
    assert "git ls-files" in ci
    assert ".playwright-cli/" in ci
    assert "config.toml" in ci or r"config\.toml" in ci
    assert "real_state 2.json" in ci or r"real_state 2\.json" in ci
