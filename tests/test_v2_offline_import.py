from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from scripts.migrate_v1_to_v2 import run_import


def test_offline_import_generates_report_and_runtime_rows(tmp_path: Path) -> None:
    cfg = tmp_path / "config.toml"
    state = tmp_path / "state.json"
    db = tmp_path / "v2.sqlite3"
    report = tmp_path / "report.json"
    cfg.write_text('[storage]\nmode="local"\n\n[[repos]]\nname="owner/repo"\n', encoding="utf-8")
    state.write_text(
        '{"version":2,"repos":{"owner/repo":{"releases":{"v1":{"downloaded_assets":["a.tgz",1,"b.zip"]}}}}}',
        encoding="utf-8",
    )

    run_import(config_path=cfg, state_path=state, db_path=db, report_path=report)
    assert report.exists()
    payload = json.loads(report.read_text(encoding="utf-8"))

    assert list(payload.keys()) == [
        "repos",
        "releases",
        "assets",
        "state_repos_detected",
        "config_repos_detected",
        "invalid_repo_keys",
        "settings_imported",
    ]
    assert payload["repos"] == 1
    assert payload["releases"] == 1
    assert payload["assets"] == 2
    assert payload["state_repos_detected"] == 1
    assert payload["config_repos_detected"] == 1
    assert payload["invalid_repo_keys"] == []
    assert payload["settings_imported"] is True

    conn = sqlite3.connect(str(db))
    try:
        repos = {row[0] for row in conn.execute("SELECT key FROM repos")}
        assert repos == {"owner/repo"}
        settings_row = conn.execute("SELECT value_json FROM app_settings WHERE key = 'global'").fetchone()
        assert settings_row is not None

        job_row = conn.execute(
            "SELECT kind, status, payload_json FROM jobs WHERE kind = 'offline_import' LIMIT 1"
        ).fetchone()
        assert job_row is not None
        assert job_row[0] == "offline_import"
        assert job_row[1] == "succeeded"
        job_payload = json.loads(job_row[2])
        assert job_payload == {
            "assets": 2,
            "invalid_repo_keys": [],
            "releases": 1,
            "repos": 1,
        }

        event_row = conn.execute(
            "SELECT event_type, payload_json FROM events ORDER BY id ASC LIMIT 1"
        ).fetchone()
        assert event_row is not None
        assert event_row[0] == "offline_import_completed"
        assert json.loads(event_row[1]) == {"repos": 1}
    finally:
        conn.close()


def test_offline_import_invalid_keys_sorted_and_settings_flag_false(tmp_path: Path) -> None:
    cfg = tmp_path / "config.toml"
    state = tmp_path / "state.json"
    db = tmp_path / "v2.sqlite3"
    report = tmp_path / "report.json"
    cfg.write_text(
        '\n'.join(
            [
                '[[repos]]',
                'name="zzz"',
                '',
                '[[repos]]',
                'name="owner/repo-b"',
                '',
                '[[repos]]',
                'name="bad"',
                '',
                '[[repos]]',
                'name="bad"',
                '',
            ]
        )
        + '\n',
        encoding="utf-8",
    )
    state.write_text(
        '{"version":2,"repos":{"owner/repo-a":{"releases":{}},"bad":{"releases":{}},"zeta":{"releases":{}}}}',
        encoding="utf-8",
    )

    run_import(config_path=cfg, state_path=state, db_path=db, report_path=report)

    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["repos"] == 2
    assert payload["state_repos_detected"] == 1
    assert payload["config_repos_detected"] == 1
    assert payload["invalid_repo_keys"] == ["bad", "zeta", "zzz"]
    assert payload["settings_imported"] is False

    conn = sqlite3.connect(str(db))
    try:
        settings_row = conn.execute("SELECT value_json FROM app_settings WHERE key = 'global'").fetchone()
        assert settings_row is None

        job_row = conn.execute(
            "SELECT payload_json FROM jobs WHERE kind = 'offline_import' LIMIT 1"
        ).fetchone()
        assert job_row is not None
        job_payload = json.loads(job_row[0])
        assert job_payload["invalid_repo_keys"] == ["bad", "zeta", "zzz"]
    finally:
        conn.close()
