from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from github_release_watcher.state import STATE_VERSION, load_state, save_state


class StateRobustnessTests(unittest.TestCase):
    def test_load_state_returns_empty_when_json_is_corrupted_and_creates_backup(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            state_path = Path(td) / "state.json"
            state_path.write_text('{"version": 1, "repos": {"a": ', encoding="utf-8")

            state = load_state(state_path)

            self.assertEqual(state, {"version": STATE_VERSION, "repos": {}})
            broken = list(Path(td).glob("state.json.broken-*"))
            self.assertEqual(len(broken), 1)
            self.assertTrue(broken[0].read_text(encoding="utf-8").startswith('{"version": 1'))

    def test_save_and_load_state_keeps_structure(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            state_path = Path(td) / "state.json"
            expected = {"version": STATE_VERSION, "repos": {"owner/repo": {"stats": {"checks_total": 1}}}}

            save_state(state_path, expected)
            actual = load_state(state_path)

            self.assertEqual(actual["version"], STATE_VERSION)
            self.assertIn("owner/repo", actual["repos"])
            self.assertEqual(actual["repos"]["owner/repo"]["stats"]["checks_total"], 1)


if __name__ == "__main__":
    unittest.main()
