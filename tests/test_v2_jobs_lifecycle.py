from __future__ import annotations

from pathlib import Path
import tempfile

from fastapi.testclient import TestClient

from github_release_watcher.v2.app import create_app


def test_job_status_flow_transitions() -> None:
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "v2.sqlite3"
        client = TestClient(create_app(db_path=db_path, auth_username="tester", auth_password="pass"))
        login = client.post("/api/v2/auth/login", json={"username": "tester", "password": "pass"})
        assert login.status_code == 200

        job = client.post("/api/v2/jobs", json={"kind": "run_repos", "payload": {"repos": ["o/r"]}}).json()
        job_id = job["id"]

        started = client.post(f"/api/v2/jobs/{job_id}/events", json={"event_type": "started", "payload": {}})
        assert started.status_code == 201
        done = client.post(f"/api/v2/jobs/{job_id}/events", json={"event_type": "succeeded", "payload": {}})
        assert done.status_code == 201

        items = client.get("/api/v2/jobs").json()["items"]
        target = [x for x in items if x["id"] == job_id][0]
        assert target["status"] == "succeeded"
