from __future__ import annotations

import unittest
from unittest.mock import patch

from github_release_watcher import cli


class V2CliTests(unittest.TestCase):
    def test_parser_accepts_web_v2_flag(self) -> None:
        parser = cli._build_parser()
        args = parser.parse_args(["--web-v2"])
        self.assertTrue(args.web_v2)

    def test_main_web_v2_dispatches_to_v2_runner(self) -> None:
        with patch("github_release_watcher.cli.ensure_rotating_file_logging"), patch(
            "github_release_watcher.cli._run_web_v2", return_value=0
        ) as run_v2:
            code = cli.main(["--web-v2", "--web-host", "0.0.0.0", "--web-port", "9000"])

        self.assertEqual(code, 0)
        run_v2.assert_called_once_with(host="0.0.0.0", port=9000, log_level="INFO")


if __name__ == "__main__":
    unittest.main()
