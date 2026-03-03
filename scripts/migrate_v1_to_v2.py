from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from github_release_watcher.v2.db import init_db


def _load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def run_import(*, config_path: Path, state_path: Path, db_path: Path, report_path: Path) -> None:
    _ = config_path
    state = _load_json(state_path)
    init_db(db_path)

    repos = state.get("repos", {}) if isinstance(state.get("repos"), dict) else {}
    repos_count = 0
    releases_count = 0
    assets_count = 0

    for _, repo_state in repos.items():
        if not isinstance(repo_state, dict):
            continue
        repos_count += 1
        releases = repo_state.get("releases", {}) if isinstance(repo_state.get("releases"), dict) else {}
        releases_count += len(releases)
        for entry in releases.values():
            if not isinstance(entry, dict):
                continue
            assets = entry.get("downloaded_assets", [])
            if isinstance(assets, list):
                assets_count += len([x for x in assets if isinstance(x, str)])

    report = {
        "repos": repos_count,
        "releases": releases_count,
        "assets": assets_count,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit("Use run_import() from automation or tests.")
