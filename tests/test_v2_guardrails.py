from __future__ import annotations

from pathlib import Path
import tempfile

from fastapi.testclient import TestClient

from github_release_watcher.v2.app import create_app


def test_v2_api_routes_use_v2_prefix_only() -> None:
    app = create_app(auth_username="tester", auth_password="pass")
    api_paths = [route.path for route in app.routes if getattr(route, "path", "").startswith("/api/")]
    assert api_paths
    assert all(path.startswith("/api/v2/") for path in api_paths)


def test_v2_job_response_does_not_include_v1_queue_status_field() -> None:
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "v2.sqlite3"
        client = TestClient(
            create_app(db_path=db_path, auth_username="tester", auth_password="pass"),
            base_url="https://testserver",
        )
        login = client.post("/api/v2/auth/login", json={"username": "tester", "password": "pass"})
        assert login.status_code == 200
        response = client.post("/api/v2/jobs", json={"kind": "run_repos", "payload": {"repos": ["owner/repo"]}})
        assert response.status_code == 201
        payload = response.json()
        assert "queue_status" not in payload


def test_ci_includes_legacy_block_step() -> None:
    ci = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "Block legacy runtime tokens" in ci
