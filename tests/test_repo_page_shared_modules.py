from __future__ import annotations

from pathlib import Path


def test_repo_js_uses_shared_api_client() -> None:
    repo_js = Path("github_release_watcher/static/repo.js").read_text(encoding="utf-8")
    assert "window.GRWApiClient?.API" in repo_js
    assert "const API = {" not in repo_js


def test_repo_html_loads_api_client_before_repo_js() -> None:
    html = Path("github_release_watcher/static/repo.html").read_text(encoding="utf-8")
    api_pos = html.find('src="/api-client.js"')
    repo_pos = html.find('src="/repo.js"')
    assert api_pos >= 0
    assert repo_pos >= 0
    assert api_pos < repo_pos
