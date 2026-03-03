from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

LATEST_STATE_VERSION = 2


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _append_history(state: dict[str, Any], *, from_version: int, to_version: int, now_iso: Callable[[], str]) -> None:
    meta = state.get("_migration", {}) if isinstance(state.get("_migration"), dict) else {}
    raw_history = meta.get("history", [])
    history = [x for x in raw_history if isinstance(x, dict)] if isinstance(raw_history, list) else []
    history.append({"from": from_version, "to": to_version, "at": now_iso()})
    meta["history"] = history[-20:]
    state["_migration"] = meta


def _migrate_v1_to_v2(state: dict[str, Any], *, now_iso: Callable[[], str]) -> dict[str, Any]:
    migrated = dict(state)
    if "repos" not in migrated or not isinstance(migrated["repos"], dict):
        migrated["repos"] = {}
    migrated["version"] = 2
    _append_history(migrated, from_version=1, to_version=2, now_iso=now_iso)
    return migrated


_MIGRATIONS: dict[tuple[int, int], Callable[[dict[str, Any]], dict[str, Any]]] = {
    (1, 2): lambda state: _migrate_v1_to_v2(state, now_iso=_now_iso),
}


def migrate_state(
    state: dict[str, Any],
    *,
    now_iso: Callable[[], str] | None = None,
) -> dict[str, Any]:
    if not isinstance(state, dict):
        raise ValueError("state must be an object")
    version_raw = state.get("version")
    if not isinstance(version_raw, int):
        raise ValueError("state.version must be an integer")

    current = dict(state)
    current_version = int(version_raw)
    if current_version == LATEST_STATE_VERSION:
        if "repos" not in current or not isinstance(current["repos"], dict):
            current["repos"] = {}
        return current

    effective_now = now_iso or _now_iso
    while current_version != LATEST_STATE_VERSION:
        step = (current_version, current_version + 1)
        migrator = _MIGRATIONS.get(step)
        if migrator is None:
            raise ValueError(f"No state migration path from version {current_version} to {LATEST_STATE_VERSION}")

        if now_iso is None:
            current = migrator(current)
        else:
            if step == (1, 2):
                current = _migrate_v1_to_v2(current, now_iso=effective_now)
            else:
                current = migrator(current)

        next_version = current.get("version")
        if not isinstance(next_version, int):
            raise ValueError("Migrated state version must be an integer")
        if next_version <= current_version:
            raise ValueError("Invalid migration step order")
        current_version = next_version

    if "repos" not in current or not isinstance(current["repos"], dict):
        current["repos"] = {}
    return current
