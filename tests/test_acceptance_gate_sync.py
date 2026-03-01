import pathlib
import shutil
import subprocess
import tempfile
import textwrap
import unittest


ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "qa" / "sync_acceptance_gates.sh"


class AcceptanceGateSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = pathlib.Path(tempfile.mkdtemp(prefix="gate-sync-"))
        self.run_dir = self.tmpdir / "run"
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.checklist = self.tmpdir / "release-acceptance-checklist.md"
        self.checklist.write_text(
            textwrap.dedent(
                """\
                ## 1. Quality Gates

                - [x] Gate 1: No open `P1/P2` defects.
                - [ ] Gate 2: Core user flows pass on desktop and mobile.
                - [ ] Gate 3: WebDAV critical flow passes end-to-end.
                - [x] Gate 4: Required automated regression commands pass.
                """
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_report(self, name: str, text: str) -> None:
        (self.run_dir / name).write_text(text, encoding="utf-8")

    def test_sync_marks_gate2_and_gate3_checked_when_reports_pass(self) -> None:
        self._write_report("gate2-report.md", "- [x] Gate 2 pass\n- [ ] Gate 2 blocked\n")
        self._write_report("gate3-report.md", "- [x] Gate 3 pass\n- [ ] Gate 3 blocked\n")

        subprocess.run(
            [str(SCRIPT), str(self.run_dir), "--checklist", str(self.checklist)],
            check=True,
            cwd=ROOT,
        )

        content = self.checklist.read_text(encoding="utf-8")
        self.assertIn("- [x] Gate 2: Core user flows pass on desktop and mobile.", content)
        self.assertIn("- [x] Gate 3: WebDAV critical flow passes end-to-end.", content)

    def test_sync_marks_unchecked_when_report_not_pass(self) -> None:
        self._write_report("gate2-report.md", "- [ ] Gate 2 pass\n- [x] Gate 2 blocked\n")
        self._write_report("gate3-report.md", "- [ ] Gate 3 pass\n- [ ] Gate 3 blocked\n")

        subprocess.run(
            [str(SCRIPT), str(self.run_dir), "--checklist", str(self.checklist)],
            check=True,
            cwd=ROOT,
        )

        content = self.checklist.read_text(encoding="utf-8")
        self.assertIn("- [ ] Gate 2: Core user flows pass on desktop and mobile.", content)
        self.assertIn("- [ ] Gate 3: WebDAV critical flow passes end-to-end.", content)

    def test_dry_run_does_not_modify_file(self) -> None:
        self._write_report("gate2-report.md", "- [x] Gate 2 pass\n- [ ] Gate 2 blocked\n")
        self._write_report("gate3-report.md", "- [x] Gate 3 pass\n- [ ] Gate 3 blocked\n")
        before = self.checklist.read_text(encoding="utf-8")

        subprocess.run(
            [str(SCRIPT), str(self.run_dir), "--checklist", str(self.checklist), "--dry-run"],
            check=True,
            cwd=ROOT,
        )

        after = self.checklist.read_text(encoding="utf-8")
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
