from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from github_release_watcher.state import STATE_VERSION, load_state
from github_release_watcher.state_migrations import LATEST_STATE_VERSION, migrate_state


def test_migrate_state_v1_to_latest_preserves_repo_payload() -> None:
    raw = {
        "version": 1,
        "repos": {
            "owner/repo": {
                "stats": {"checks_total": 3},
                "releases": {"v1": {"downloaded_assets": ["a.zip"]}},
            }
        },
    }

    migrated = migrate_state(raw, now_iso=lambda: "2026-03-03T00:00:00+00:00")

    assert migrated["version"] == LATEST_STATE_VERSION
    assert migrated["repos"]["owner/repo"]["stats"]["checks_total"] == 3
    history = migrated.get("_migration", {}).get("history", [])
    assert history
    assert history[-1]["from"] == 1
    assert history[-1]["to"] == LATEST_STATE_VERSION
    assert history[-1]["at"] == "2026-03-03T00:00:00+00:00"


def test_load_state_migrates_supported_legacy_version() -> None:
    with tempfile.TemporaryDirectory() as td:
        state_path = Path(td) / "state.json"
        state_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "repos": {
                        "owner/repo": {
                            "stats": {"checks_total": 7},
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

        state = load_state(state_path)

        assert state["version"] == STATE_VERSION
        assert state["repos"]["owner/repo"]["stats"]["checks_total"] == 7
        assert state.get("_migration", {}).get("history")


def test_load_state_falls_back_when_version_is_not_migratable() -> None:
    with tempfile.TemporaryDirectory() as td:
        state_path = Path(td) / "state.json"
        state_path.write_text(
            json.dumps({"version": 999, "repos": {"owner/repo": {"stats": {"checks_total": 1}}}}),
            encoding="utf-8",
        )

        state = load_state(state_path)

        assert state == {"version": STATE_VERSION, "repos": {}}


def test_migrate_state_raises_for_unknown_path() -> None:
    with pytest.raises(ValueError, match="No state migration path"):
        migrate_state({"version": 0, "repos": {}})
