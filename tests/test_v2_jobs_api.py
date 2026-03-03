from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from github_release_watcher.v2.app import create_app


class V2JobsApiTests(unittest.TestCase):
    def test_enqueue_and_list_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "v2.sqlite3"
            client = TestClient(create_app(db_path=db_path))

            enqueue = client.post(
                "/api/v2/jobs",
                json={"kind": "run_repos", "payload": {"repos": ["owner/repo"]}},
            )

            self.assertEqual(enqueue.status_code, 201)
            created = enqueue.json()
            self.assertEqual(created.get("kind"), "run_repos")
            self.assertEqual(created.get("status"), "queued")
            self.assertIsInstance(created.get("id"), str)

            listing = client.get("/api/v2/jobs")
            self.assertEqual(listing.status_code, 200)
            items = listing.json().get("items")
            self.assertIsInstance(items, list)
            self.assertGreaterEqual(len(items), 1)
            self.assertIn(created["id"], {item.get("id") for item in items if isinstance(item, dict)})


if __name__ == "__main__":
    unittest.main()
