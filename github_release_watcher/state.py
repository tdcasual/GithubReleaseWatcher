from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATE_VERSION = 1


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": STATE_VERSION, "repos": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {"version": STATE_VERSION, "repos": {}}
    if data.get("version") != STATE_VERSION:
        return {"version": STATE_VERSION, "repos": {}}
    if "repos" not in data or not isinstance(data["repos"], dict):
        data["repos"] = {}
    return data


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp_path.replace(path)


def get_repo_state(state: dict[str, Any], repo_key: str) -> dict[str, Any]:
    repos = state.setdefault("repos", {})
    repo_state = repos.setdefault(repo_key, {})
    repo_state.setdefault("releases", {})
    return repo_state


def mark_release_processed(
    repo_state: dict[str, Any],
    tag: str,
    downloaded_assets: list[str],
) -> None:
    releases = repo_state.setdefault("releases", {})
    releases[tag] = {
        "processed_at": _now_iso(),
        "downloaded_assets": sorted(set(downloaded_assets)),
    }


def remove_release_state(repo_state: dict[str, Any], tag: str) -> None:
    releases = repo_state.get("releases", {})
    if isinstance(releases, dict):
        releases.pop(tag, None)

