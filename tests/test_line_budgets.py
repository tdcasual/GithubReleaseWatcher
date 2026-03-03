from __future__ import annotations

from pathlib import Path


def _line_count(path: str) -> int:
    return len(Path(path).read_text(encoding="utf-8").splitlines())


def test_webapp_py_line_budget() -> None:
    assert _line_count("github_release_watcher/webapp.py") <= 1200


def test_frontend_app_js_line_budget() -> None:
    assert _line_count("github_release_watcher/static/app.js") <= 1200
