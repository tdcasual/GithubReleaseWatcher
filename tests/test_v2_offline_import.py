from __future__ import annotations

from pathlib import Path

from scripts.migrate_v1_to_v2 import run_import


def test_offline_import_generates_report(tmp_path: Path) -> None:
    cfg = tmp_path / "config.toml"
    state = tmp_path / "state.json"
    db = tmp_path / "v2.sqlite3"
    report = tmp_path / "report.json"
    cfg.write_text('[[repos]]\nname="owner/repo"\n', encoding="utf-8")
    state.write_text('{"version":2,"repos":{"owner/repo":{"releases":{}}}}', encoding="utf-8")
    run_import(config_path=cfg, state_path=state, db_path=db, report_path=report)
    assert report.exists()
