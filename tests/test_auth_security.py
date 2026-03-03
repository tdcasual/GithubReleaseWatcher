from __future__ import annotations

import unittest

from github_release_watcher import webapp


class _FakeApp:
    def __init__(self, allow_login: bool):
        self._allow_login = allow_login

    def verify_login(self, username: str, password: str) -> bool:
        return self._allow_login


class AuthSecurityTests(unittest.TestCase):
    def test_load_auth_config_marks_default_credentials_as_must_change(self) -> None:
        cfg = webapp._load_auth_config({})
        self.assertTrue(bool(cfg.get("must_change_password")))
        self.assertEqual(str(cfg.get("username") or ""), "admin")
        self.assertFalse(webapp._verify_password("admin", cfg))

    def test_login_rate_limit_blocks_repeated_failures(self) -> None:
        auth = webapp.AuthService(_FakeApp(allow_login=False), session_ttl_seconds=300)
        error_codes = []
        for _ in range(7):
            token, error = auth.login("admin", "wrong", "127.0.0.1")
            self.assertIsNone(token)
            error_codes.append(error)

        self.assertIn("rate_limited", error_codes)

    def test_load_auth_config_preserves_must_change_password_flag(self) -> None:
        salt = "ab" * 16
        iterations = 200_000
        password_hash = webapp._pbkdf2_hash("s3cret-pass", salt_hex=salt, iterations=iterations)
        cfg = webapp._load_auth_config(
            {
                "auth": {
                    "username": "tester",
                    "salt": salt,
                    "iterations": iterations,
                    "password_hash": password_hash,
                    "must_change_password": True,
                }
            }
        )
        self.assertTrue(bool(cfg.get("must_change_password")))


if __name__ == "__main__":
    unittest.main()
