from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from scripts.migrate_v1_to_v2 import run_import


def test_offline_import_generates_report(tmp_path: Path) -> None:
    cfg = tmp_path / "config.toml"
    state = tmp_path / "state.json"
    db = tmp_path / "v2.sqlite3"
    report = tmp_path / "report.json"
    cfg.write_text('[storage]\nmode="local"\n\n[[repos]]\nname="owner/repo"\n', encoding="utf-8")
    state.write_text('{"version":2,"repos":{"owner/repo":{"releases":{}}}}', encoding="utf-8")
    run_import(config_path=cfg, state_path=state, db_path=db, report_path=report)
    assert report.exists()
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["repos"] == 1

    conn = sqlite3.connect(str(db))
    try:
        repos = {row[0] for row in conn.execute("SELECT key FROM repos")}
        assert repos == {"owner/repo"}
        settings_row = conn.execute("SELECT value_json FROM app_settings WHERE key = 'global'").fetchone()
        assert settings_row is not None
    finally:
        conn.close()
