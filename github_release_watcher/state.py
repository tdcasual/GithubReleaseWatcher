from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATE_VERSION = 1
DEFAULT_ACTIVITY_CAPACITY = 500


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
    if not isinstance(repo_state, dict):
        repo_state = {}
        repos[repo_key] = repo_state
    repo_state.setdefault("releases", {})
    repo_state.setdefault("stats", {})
    repo_state.setdefault("update", {})
    repo_state.setdefault("activity", [])
    return repo_state


def mark_release_processed(
    repo_state: dict[str, Any],
    tag: str,
    downloaded_assets: list[str],
    *,
    published_at: str | None = None,
    created_at: str | None = None,
    html_url: str | None = None,
) -> None:
    releases = repo_state.setdefault("releases", {})
    releases[tag] = {
        "processed_at": _now_iso(),
        "published_at": published_at,
        "created_at": created_at,
        "html_url": html_url,
        "downloaded_assets": sorted(set(downloaded_assets)),
    }


def remove_release_state(repo_state: dict[str, Any], tag: str) -> None:
    releases = repo_state.get("releases", {})
    if isinstance(releases, dict):
        releases.pop(tag, None)


def append_repo_activity(repo_state: dict[str, Any], event: dict[str, Any], *, capacity: int = DEFAULT_ACTIVITY_CAPACITY) -> None:
    if not isinstance(event, dict):
        return
    event.setdefault("time", _now_iso())
    items = repo_state.setdefault("activity", [])
    if not isinstance(items, list):
        items = []
        repo_state["activity"] = items

    items.append(event)
    cap = max(50, int(capacity))
    if len(items) > cap:
        repo_state["activity"] = items[-cap:]
