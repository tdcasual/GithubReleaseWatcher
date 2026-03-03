from __future__ import annotations

from fastapi.testclient import TestClient

from github_release_watcher.v2.app import create_app


def test_v2_health_endpoint_returns_ok() -> None:
    client = TestClient(create_app(auth_username="tester", auth_password="pass"), base_url="https://testserver")

    response = client.get("/api/v2/health")

    assert response.status_code == 200
    assert response.json() == {"ok": True, "api_version": "v2"}
