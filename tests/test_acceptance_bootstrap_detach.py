import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parent.parent
BOOTSTRAP = ROOT / "scripts" / "qa" / "manual_acceptance_bootstrap.sh"


class AcceptanceBootstrapDetachTests(unittest.TestCase):
    def test_bootstrap_uses_nohup_detached_start(self) -> None:
        content = BOOTSTRAP.read_text(encoding="utf-8")
        # Ensure background service survives shell exit in CI/automation shells.
        self.assertIn("nohup", content, "bootstrap script should launch watcher via nohup")
        self.assertIn("</dev/null", content, "bootstrap script should close stdin for detached run")


if __name__ == "__main__":
    unittest.main()
