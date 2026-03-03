from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from github_release_watcher.v2.db import connect_db, init_db

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore


def _load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _load_toml(path: Path) -> dict[str, Any]:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _is_repo_key(raw: Any) -> bool:
    value = str(raw or "").strip()
    if "/" not in value:
        return False
    owner, repo = value.split("/", 1)
    return bool(owner.strip() and repo.strip())


def _normalize_repo_from_config(entry: dict[str, Any]) -> tuple[str, bool, dict[str, Any]] | None:
    key = str(entry.get("name") or "").strip()
    if not _is_repo_key(key):
        return None
    policy: dict[str, Any] = {}
    for field in ("include_assets", "exclude_assets", "asset_types", "include_prereleases", "include_drafts", "keep_last"):
        if field in entry:
            policy[field] = entry[field]
    return key, bool(entry.get("enabled", True)), policy


def _settings_from_config(config: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if "interval_seconds" in config:
        payload["scheduler"] = {
            "enabled": True,
            "interval_seconds": int(config.get("interval_seconds") or 0),
        }
    if "keep_last" in config:
        payload["retention"] = {"keep_last": int(config.get("keep_last") or 0)}

    storage = config.get("storage")
    if isinstance(storage, dict):
        out_storage: dict[str, Any] = {}
        mode = storage.get("mode")
        if isinstance(mode, str) and mode.strip():
            out_storage["mode"] = mode.strip().lower()
        webdav = storage.get("webdav")
        if isinstance(webdav, dict):
            out_storage["webdav"] = {
                "base_url": str(webdav.get("base_url") or ""),
                "username": str(webdav.get("username") or ""),
                "verify_tls": bool(webdav.get("verify_tls", True)),
                "timeout_seconds": int(webdav.get("timeout_seconds") or 60),
            }
        if out_storage:
            payload["storage"] = out_storage

    return payload


def run_import(*, config_path: Path, state_path: Path, db_path: Path, report_path: Path) -> None:
    config = _load_toml(config_path)
    state = _load_json(state_path)
    init_db(db_path)

    repos = state.get("repos", {}) if isinstance(state.get("repos"), dict) else {}
    repos_count_state = 0
    repos_upserted = 0
    releases_count = 0
    assets_count = 0
    invalid_repo_keys: list[str] = []
    config_repo_map: dict[str, tuple[bool, dict[str, Any]]] = {}

    raw_config_repos = config.get("repos")
    if isinstance(raw_config_repos, list):
        for entry in raw_config_repos:
            if not isinstance(entry, dict):
                continue
            parsed = _normalize_repo_from_config(entry)
            if parsed is None:
                bad = str(entry.get("name") or "").strip()
                if bad:
                    invalid_repo_keys.append(bad)
                continue
            key, enabled, policy = parsed
            config_repo_map[key] = (enabled, policy)

    state_repo_keys = {str(key).strip() for key in repos.keys() if _is_repo_key(key)}
    for key in repos.keys():
        key_text = str(key).strip()
        if key_text and key_text not in state_repo_keys:
            invalid_repo_keys.append(key_text)

    all_repo_keys = sorted(state_repo_keys | set(config_repo_map.keys()))
    now = _now_iso()
    conn = connect_db(db_path)
    try:
        for repo_key in all_repo_keys:
            state_repo = repos.get(repo_key)
            if isinstance(state_repo, dict):
                repos_count_state += 1
            enabled, policy = config_repo_map.get(repo_key, (True, {}))
            conn.execute(
                """
                INSERT INTO repos(id, key, enabled, policy_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    enabled = excluded.enabled,
                    policy_json = excluded.policy_json,
                    updated_at = excluded.updated_at
                """,
                (
                    uuid.uuid4().hex,
                    repo_key,
                    1 if enabled else 0,
                    json.dumps(policy, ensure_ascii=False, sort_keys=True),
                    now,
                    now,
                ),
            )
            repos_upserted += 1

            if isinstance(state_repo, dict):
                releases = state_repo.get("releases", {}) if isinstance(state_repo.get("releases"), dict) else {}
                releases_count += len(releases)
                for release_entry in releases.values():
                    if not isinstance(release_entry, dict):
                        continue
                    assets = release_entry.get("downloaded_assets", [])
                    if isinstance(assets, list):
                        assets_count += len([x for x in assets if isinstance(x, str)])

        settings_payload = _settings_from_config(config)
        settings_imported = bool(settings_payload)
        if settings_imported:
            conn.execute(
                """
                INSERT INTO app_settings(key, value_json, updated_at)
                VALUES ('global', ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value_json = excluded.value_json,
                    updated_at = excluded.updated_at
                """,
                (json.dumps(settings_payload, ensure_ascii=False, sort_keys=True), now),
            )
        else:
            settings_imported = False

        import_job_id = f"offline_import_{uuid.uuid4().hex}"
        job_payload = {
            "repos": repos_upserted,
            "releases": releases_count,
            "assets": assets_count,
            "invalid_repo_keys": invalid_repo_keys,
        }
        conn.execute(
            """
            INSERT INTO jobs(id, kind, status, payload_json, error_text, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                import_job_id,
                "offline_import",
                "succeeded",
                json.dumps(job_payload, ensure_ascii=False, sort_keys=True),
                None,
                now,
                now,
            ),
        )
        conn.execute(
            """
            INSERT INTO events(job_id, event_type, payload_json, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                import_job_id,
                "offline_import_completed",
                json.dumps({"repos": repos_upserted}, ensure_ascii=False, sort_keys=True),
                now,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    report = {
        "repos": repos_upserted,
        "releases": releases_count,
        "assets": assets_count,
        "state_repos_detected": repos_count_state,
        "config_repos_detected": len(config_repo_map),
        "invalid_repo_keys": invalid_repo_keys,
        "settings_imported": settings_imported,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit("Use run_import() from automation or tests.")
