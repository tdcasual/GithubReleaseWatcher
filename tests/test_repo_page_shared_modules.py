from __future__ import annotations

from pathlib import Path


def test_repo_js_uses_shared_api_client() -> None:
    repo_js = Path("github_release_watcher/static/repo.js").read_text(encoding="utf-8")
    assert "window.GRWApiClient?.API" in repo_js
    assert "window.GRWFormatters" in repo_js
    assert "window.GRWAppUiUtils" in repo_js
    assert "window.GRWAppAuth" in repo_js
    assert "const API = {" not in repo_js
    assert "function toast(" not in repo_js
    assert "function setButtonBusy(" not in repo_js
    assert "async function startLoginFlow(" not in repo_js
    assert "async function requireLogin(" not in repo_js
    assert "function isoToLocal(" not in repo_js


def test_repo_html_loads_api_client_before_repo_js() -> None:
    html = Path("github_release_watcher/static/repo.html").read_text(encoding="utf-8")
    api_pos = html.find('src="/api-client.js"')
    formatters_pos = html.find('src="/formatters.js"')
    mobile_behavior_pos = html.find('src="/mobile-behavior.js"')
    app_ui_utils_pos = html.find('src="/app-ui-utils.js"')
    app_auth_pos = html.find('src="/app-auth.js"')
    repo_pos = html.find('src="/repo.js"')
    assert api_pos >= 0
    assert formatters_pos >= 0
    assert mobile_behavior_pos >= 0
    assert app_ui_utils_pos >= 0
    assert app_auth_pos >= 0
    assert repo_pos >= 0
    assert api_pos < repo_pos
    assert formatters_pos < repo_pos
    assert mobile_behavior_pos < repo_pos
    assert app_ui_utils_pos < repo_pos
    assert app_auth_pos < repo_pos
