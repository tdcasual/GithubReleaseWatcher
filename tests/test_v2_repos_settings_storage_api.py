from __future__ import annotations

from pathlib import Path
import tempfile

from fastapi.testclient import TestClient

from github_release_watcher.v2.app import create_app


def test_v2_settings_and_repos_roundtrip() -> None:
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "v2.sqlite3"
        client = TestClient(
            create_app(db_path=db_path, auth_username="tester", auth_password="pass"),
            base_url="https://testserver",
        )
        login = client.post("/api/v2/auth/login", json={"username": "tester", "password": "pass"})
        assert login.status_code == 200

        put = client.put("/api/v2/settings", json={"scheduler": {"enabled": True}, "storage": {"mode": "local"}})
        assert put.status_code == 200

        post_repo = client.post("/api/v2/repos", json={"key": "owner/repo", "enabled": True})
        assert post_repo.status_code == 201

        listing = client.get("/api/v2/repos").json()["items"]
        assert any(item["key"] == "owner/repo" for item in listing)

        storage = client.get("/api/v2/storage/health")
        assert storage.status_code == 200
        storage_payload = storage.json()
        assert storage_payload.get("mode") == "local"
        assert storage_payload.get("source") == "storage_health_service"
        assert isinstance(storage_payload.get("checked_at"), str)


def test_v2_repos_rejects_invalid_key_with_400() -> None:
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "v2.sqlite3"
        client = TestClient(
            create_app(db_path=db_path, auth_username="tester", auth_password="pass"),
            raise_server_exceptions=False,
            base_url="https://testserver",
        )
        login = client.post("/api/v2/auth/login", json={"username": "tester", "password": "pass"})
        assert login.status_code == 200

        bad = client.post("/api/v2/repos", json={"key": "not-a-repo", "enabled": True})
        assert bad.status_code == 400
        assert "owner/repo" in bad.text


def test_storage_health_defaults_when_settings_missing() -> None:
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "v2.sqlite3"
        client = TestClient(
            create_app(db_path=db_path, auth_username="tester", auth_password="pass"),
            base_url="https://testserver",
        )
        login = client.post("/api/v2/auth/login", json={"username": "tester", "password": "pass"})
        assert login.status_code == 200

        storage = client.get("/api/v2/storage/health")
        assert storage.status_code == 200
        payload = storage.json()
        assert payload.get("mode") == "local"
        assert payload.get("settings_updated_at") is None
        assert payload.get("source") == "storage_health_service"
        assert isinstance(payload.get("checked_at"), str)


def test_storage_health_reflects_webdav_mode() -> None:
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "v2.sqlite3"
        client = TestClient(
            create_app(db_path=db_path, auth_username="tester", auth_password="pass"),
            base_url="https://testserver",
        )
        login = client.post("/api/v2/auth/login", json={"username": "tester", "password": "pass"})
        assert login.status_code == 200

        put = client.put(
            "/api/v2/settings",
            json={
                "storage": {
                    "mode": "webdav",
                    "webdav": {"base_url": "https://example.invalid/dav", "verify_tls": True},
                }
            },
        )
        assert put.status_code == 200

        storage = client.get("/api/v2/storage/health")
        assert storage.status_code == 200
        payload = storage.json()
        assert payload.get("mode") == "webdav"
        assert payload.get("source") == "storage_health_service"
        assert isinstance(payload.get("checked_at"), str)
        assert isinstance(payload.get("settings_updated_at"), str)
