from __future__ import annotations

from pathlib import Path


def test_webapp_handler_delegates_to_router_module() -> None:
    source = Path("github_release_watcher/webapp.py").read_text(encoding="utf-8")
    assert "from .webapp_api_router import handle_api_request" in source
    assert "handle_api_request(self, path, split)" in source
