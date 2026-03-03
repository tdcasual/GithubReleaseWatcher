#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

python3 - <<'PY'
from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from github_release_watcher.v2.app import create_app


with tempfile.TemporaryDirectory() as td:
    db_path = Path(td) / "v2.sqlite3"
    client = TestClient(
        create_app(db_path=db_path, auth_username="tester", auth_password="pass"),
        base_url="https://testserver",
    )

    health = client.get("/api/v2/health")
    assert health.status_code == 200, health.text
    assert health.json().get("ok") is True
    print("[smoke] health ok")

    login = client.post("/api/v2/auth/login", json={"username": "tester", "password": "pass"})
    assert login.status_code == 200, login.text
    assert login.json().get("ok") is True
    assert "grw_v2_session" in login.cookies
    print("[smoke] login ok")

    settings = client.put(
        "/api/v2/settings",
        json={"scheduler": {"enabled": True, "interval_seconds": 60}, "storage": {"mode": "local"}},
    )
    assert settings.status_code == 200, settings.text
    print("[smoke] settings ok")

    repo = client.post("/api/v2/repos", json={"key": "owner/repo", "enabled": True})
    assert repo.status_code == 201, repo.text
    repo_id = repo.json().get("id")
    assert isinstance(repo_id, str) and repo_id
    print("[smoke] repo create ok")

    job = client.post("/api/v2/jobs", json={"kind": "run_repos", "payload": {"repos": ["owner/repo"]}})
    assert job.status_code == 201, job.text
    job_id = job.json().get("id")
    assert isinstance(job_id, str) and job_id
    print("[smoke] job enqueue ok")

    started = client.post(f"/api/v2/jobs/{job_id}/events", json={"event_type": "started", "payload": {}})
    assert started.status_code == 201, started.text
    done = client.post(f"/api/v2/jobs/{job_id}/events", json={"event_type": "succeeded", "payload": {}})
    assert done.status_code == 201, done.text
    print("[smoke] job events ok")

    jobs = client.get("/api/v2/jobs?limit=10")
    assert jobs.status_code == 200, jobs.text
    items = jobs.json().get("items", [])
    assert any(isinstance(item, dict) and item.get("id") == job_id and item.get("status") == "succeeded" for item in items)
    print("[smoke] jobs list ok")

    events = client.get(f"/api/v2/events?job_id={job_id}&limit=10")
    assert events.status_code == 200, events.text
    event_items = events.json().get("items", [])
    assert len(event_items) >= 2
    print("[smoke] events list ok")

    storage = client.get("/api/v2/storage/health")
    assert storage.status_code == 200, storage.text
    assert storage.json().get("mode") == "local"
    print("[smoke] storage health ok")

print("[smoke] v2 api flow ok")
PY
