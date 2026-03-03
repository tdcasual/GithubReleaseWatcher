from __future__ import annotations

from pathlib import Path


def test_bootstrap_contract_module_exists_and_exports_contract() -> None:
    source = Path("github_release_watcher/static/bootstrap-contract.js")
    assert source.exists()
    text = source.read_text(encoding="utf-8")

    assert "window.GRWBootstrapContract" in text
    assert "contract_version" in text
    assert "requireModules" in text


def test_repo_html_loads_bootstrap_contract_before_repo_js() -> None:
    html = Path("github_release_watcher/static/repo.html").read_text(encoding="utf-8")
    bootstrap_pos = html.find('src="/bootstrap-contract.js"')
    repo_pos = html.find('src="/repo.js"')
    assert bootstrap_pos >= 0
    assert repo_pos >= 0
    assert bootstrap_pos < repo_pos


def test_app_and_repo_entrypoints_use_bootstrap_contract_validation() -> None:
    app_js = Path("github_release_watcher/static/app.js").read_text(encoding="utf-8")
    repo_js = Path("github_release_watcher/static/repo.js").read_text(encoding="utf-8")

    assert "window.GRWBootstrapContract" in app_js
    assert "requireModules(" in app_js
    assert "window.GRWBootstrapContract" in repo_js
    assert "requireModules(" in repo_js
