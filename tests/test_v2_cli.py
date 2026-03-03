from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from github_release_watcher import cli


class V2CliTests(unittest.TestCase):
    def test_parser_accepts_web_flag(self) -> None:
        parser = cli._build_parser()
        args = parser.parse_args(["--web"])
        self.assertTrue(args.web)

    def test_main_web_dispatches_to_v2_runner(self) -> None:
        with patch("github_release_watcher.cli._run_web_v2", return_value=0) as run_v2:
            code = cli.main(
                [
                    "--web",
                    "--web-host",
                    "0.0.0.0",
                    "--web-port",
                    "9000",
                    "--auth-username",
                    "tester",
                    "--auth-password",
                    "pass",
                ]
            )

        self.assertEqual(code, 0)
        run_v2.assert_called_once_with(
            host="0.0.0.0",
            port=9000,
            log_level="INFO",
            db_path=Path("v2.sqlite3"),
            auth_username="tester",
            auth_password="pass",
            session_cookie_secure=True,
        )

    def test_main_rejects_missing_auth_credentials(self) -> None:
        with patch("github_release_watcher.cli._run_web_v2", return_value=0) as run_v2:
            code = cli.main(["--web"])
        self.assertEqual(code, 2)
        run_v2.assert_not_called()

    def test_main_allows_insecure_cookie_override(self) -> None:
        with patch("github_release_watcher.cli._run_web_v2", return_value=0) as run_v2:
            code = cli.main(
                [
                    "--web",
                    "--auth-username",
                    "tester",
                    "--auth-password",
                    "pass",
                    "--insecure-cookie",
                ]
            )

        self.assertEqual(code, 0)
        run_v2.assert_called_once_with(
            host="127.0.0.1",
            port=8000,
            log_level="INFO",
            db_path=Path("v2.sqlite3"),
            auth_username="tester",
            auth_password="pass",
            session_cookie_secure=False,
        )


if __name__ == "__main__":
    unittest.main()
