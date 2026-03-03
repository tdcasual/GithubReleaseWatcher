from __future__ import annotations

import pathlib
import shutil
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "qa" / "new_gate4_report.sh"


class Gate4ReportScriptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = pathlib.Path(tempfile.mkdtemp(prefix="gate4-report-"))
        self.run_dir = self.tmpdir / "run"
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.commands_file = self.tmpdir / "commands.txt"

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_generate_pass_report_from_commands_file(self) -> None:
        self.commands_file.write_text(
            "\n".join(
                [
                    "sync|echo ok-sync",
                    "tests|echo ok-tests",
                    "syntax|echo ok-syntax",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        subprocess.run(
            [str(SCRIPT), str(self.run_dir), "--commands-file", str(self.commands_file)],
            check=True,
            cwd=ROOT,
        )

        report = (self.run_dir / "gate4-report.md").read_text(encoding="utf-8")
        self.assertIn("- [x] Gate 4 pass", report)
        self.assertIn("- [ ] Gate 4 blocked", report)
        self.assertIn("ok-sync", report)

    def test_generate_blocked_report_and_strict_exit_code(self) -> None:
        self.commands_file.write_text(
            "\n".join(
                [
                    "sync|echo ok-sync",
                    "tests|bash -lc 'echo failing-test >&2; exit 7'",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        non_strict = subprocess.run(
            [str(SCRIPT), str(self.run_dir), "--commands-file", str(self.commands_file)],
            check=False,
            cwd=ROOT,
        )
        self.assertEqual(non_strict.returncode, 0)

        report = (self.run_dir / "gate4-report.md").read_text(encoding="utf-8")
        self.assertIn("- [ ] Gate 4 pass", report)
        self.assertIn("- [x] Gate 4 blocked", report)
        self.assertIn("failing-test", report)

        strict = subprocess.run(
            [str(SCRIPT), str(self.run_dir), "--commands-file", str(self.commands_file), "--strict"],
            check=False,
            cwd=ROOT,
        )
        self.assertEqual(strict.returncode, 2)


if __name__ == "__main__":
    unittest.main()
