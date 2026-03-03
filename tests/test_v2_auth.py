from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from github_release_watcher.v2.app import create_app


class V2AuthTests(unittest.TestCase):
    def test_login_sets_cookie_and_allows_protected_endpoint(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "v2.sqlite3"
            client = TestClient(create_app(db_path=db_path, auth_username="tester", auth_password="pass"))

            unauth = client.get("/api/v2/jobs")
            self.assertEqual(unauth.status_code, 401)

            login = client.post("/api/v2/auth/login", json={"username": "tester", "password": "pass"})
            self.assertEqual(login.status_code, 200)
            self.assertEqual(login.json().get("ok"), True)
            self.assertIn("grw_v2_session", login.cookies)

            protected = client.get("/api/v2/jobs")
            self.assertEqual(protected.status_code, 200)

    def test_login_rejects_invalid_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "v2.sqlite3"
            client = TestClient(create_app(db_path=db_path, auth_username="tester", auth_password="pass"))

            login = client.post("/api/v2/auth/login", json={"username": "tester", "password": "wrong"})
            self.assertEqual(login.status_code, 401)
            self.assertEqual(login.json().get("error"), "invalid_credentials")


if __name__ == "__main__":
    unittest.main()
