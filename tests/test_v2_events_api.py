from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from github_release_watcher.v2.app import create_app


class V2EventsApiTests(unittest.TestCase):
    def test_append_and_list_events(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "v2.sqlite3"
            client = TestClient(create_app(db_path=db_path, auth_username="tester", auth_password="pass"))

            login = client.post("/api/v2/auth/login", json={"username": "tester", "password": "pass"})
            self.assertEqual(login.status_code, 200)

            create_job = client.post(
                "/api/v2/jobs",
                json={"kind": "run_repos", "payload": {"repos": ["owner/repo"]}},
            )
            self.assertEqual(create_job.status_code, 201)
            job_id = create_job.json().get("id")
            self.assertIsInstance(job_id, str)

            add_event = client.post(
                f"/api/v2/jobs/{job_id}/events",
                json={"event_type": "job_started", "payload": {"step": "download"}},
            )
            self.assertEqual(add_event.status_code, 201)
            event = add_event.json()
            self.assertEqual(event.get("job_id"), job_id)
            self.assertEqual(event.get("event_type"), "job_started")
            self.assertEqual(event.get("payload"), {"step": "download"})

            listing = client.get("/api/v2/events?limit=10")
            self.assertEqual(listing.status_code, 200)
            items = listing.json().get("items")
            self.assertIsInstance(items, list)
            self.assertGreaterEqual(len(items), 1)
            self.assertIn(event.get("id"), {x.get("id") for x in items if isinstance(x, dict)})


if __name__ == "__main__":
    unittest.main()
