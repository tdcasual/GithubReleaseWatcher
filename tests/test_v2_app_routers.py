from __future__ import annotations

from github_release_watcher.v2.app import create_app


def test_v2_app_registers_router_modules() -> None:
    app = create_app()
    paths = {route.path for route in app.routes}
    assert "/api/v2/auth/login" in paths
    assert "/api/v2/jobs" in paths
    assert "/api/v2/events" in paths
    assert "/api/v2/repos" in paths
    assert "/api/v2/settings" in paths
    assert "/api/v2/storage/health" in paths
