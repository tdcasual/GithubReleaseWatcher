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
            code = cli.main(["--web", "--web-host", "0.0.0.0", "--web-port", "9000"])

        self.assertEqual(code, 0)
        run_v2.assert_called_once_with(
            host="0.0.0.0",
            port=9000,
            log_level="INFO",
            db_path=Path("v2.sqlite3"),
            auth_username="admin",
            auth_password="admin",
        )


if __name__ == "__main__":
    unittest.main()
