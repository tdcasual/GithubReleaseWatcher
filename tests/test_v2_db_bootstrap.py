from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from github_release_watcher.v2.db import init_db


class V2DatabaseBootstrapTests(unittest.TestCase):
    def test_init_db_creates_core_tables_and_status_constraint(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "v2.sqlite3"
            init_db(db_path)

            conn = sqlite3.connect(str(db_path))
            try:
                tables = {
                    row[0]
                    for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
                    if isinstance(row[0], str)
                }
                self.assertIn("repos", tables)
                self.assertIn("jobs", tables)
                self.assertIn("events", tables)
                self.assertIn("sessions", tables)
                self.assertIn("app_settings", tables)

                conn.execute(
                    "INSERT INTO jobs(id, kind, status, payload_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                    ("job-ok", "run_repos", "queued", "{}", "2026-03-03T00:00:00+00:00", "2026-03-03T00:00:00+00:00"),
                )

                with self.assertRaises(sqlite3.IntegrityError):
                    conn.execute(
                        "INSERT INTO jobs(id, kind, status, payload_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                        ("job-bad", "run_repos", "invalid_status", "{}", "2026-03-03T00:00:00+00:00", "2026-03-03T00:00:00+00:00"),
                    )
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
