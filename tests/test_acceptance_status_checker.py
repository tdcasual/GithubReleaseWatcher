from __future__ import annotations

import pathlib
import shutil
import subprocess
import tempfile
import textwrap
import unittest


ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "qa" / "check_acceptance_status.sh"


class AcceptanceStatusCheckerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = pathlib.Path(tempfile.mkdtemp(prefix="acceptance-status-"))
        self.run_dir = self.tmpdir / "run"
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.checklist = self.tmpdir / "release-acceptance-checklist.md"
        self.checklist.write_text(
            textwrap.dedent(
                """\
                ## 1. Quality Gates

                - [x] Gate 1: No open `P1/P2` defects.
                - [x] Gate 2: Core user flows pass on desktop and mobile.
                - [x] Gate 3: WebDAV critical flow passes end-to-end.
                - [x] Gate 4: Required automated regression commands pass.
                """
            ),
            encoding="utf-8",
        )
        (self.run_dir / "gate2-report.md").write_text("- [x] Gate 2 pass\n- [ ] Gate 2 blocked\n", encoding="utf-8")
        (self.run_dir / "gate3-report.md").write_text("- [x] Gate 3 pass\n- [ ] Gate 3 blocked\n", encoding="utf-8")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_strict_ready_when_gate4_report_pass(self) -> None:
        (self.run_dir / "gate4-report.md").write_text("- [x] Gate 4 pass\n- [ ] Gate 4 blocked\n", encoding="utf-8")
        proc = subprocess.run(
            [str(SCRIPT), str(self.run_dir), "--checklist", str(self.checklist), "--strict"],
            check=False,
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("Gate 4 report: PASS", proc.stdout)
        self.assertIn("Release readiness: READY", proc.stdout)

    def test_strict_blocked_when_gate4_report_not_pass(self) -> None:
        (self.run_dir / "gate4-report.md").write_text("- [ ] Gate 4 pass\n- [x] Gate 4 blocked\n", encoding="utf-8")
        proc = subprocess.run(
            [str(SCRIPT), str(self.run_dir), "--checklist", str(self.checklist), "--strict"],
            check=False,
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("Gate 4 report: BLOCKED", proc.stdout)
        self.assertIn("Gate 4 report is not PASS.", proc.stdout)


if __name__ == "__main__":
    unittest.main()
