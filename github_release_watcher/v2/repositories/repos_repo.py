from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..db import connect_db


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def add_repo(*, db_path: Path, key: str, enabled: bool, policy: dict[str, Any] | None = None) -> dict[str, Any]:
    repo_id = uuid.uuid4().hex
    now = _now_iso()
    policy_json = json.dumps(policy or {}, ensure_ascii=False, sort_keys=True)
    conn = connect_db(db_path)
    try:
        conn.execute(
            "INSERT INTO repos(id, key, enabled, policy_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (repo_id, key, 1 if enabled else 0, policy_json, now, now),
        )
        conn.commit()
    finally:
        conn.close()
    return {"id": repo_id, "key": key, "enabled": bool(enabled), "policy": policy or {}, "created_at": now, "updated_at": now}


def list_repos(*, db_path: Path, limit: int = 500) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit), 5000))
    conn = connect_db(db_path)
    try:
        rows = conn.execute(
            "SELECT id, key, enabled, policy_json, created_at, updated_at FROM repos ORDER BY key ASC LIMIT ?",
            (safe_limit,),
        ).fetchall()
    finally:
        conn.close()

    items: list[dict[str, Any]] = []
    for row in rows:
        try:
            policy = json.loads(row["policy_json"]) if isinstance(row["policy_json"], str) else {}
        except Exception:
            policy = {}
        if not isinstance(policy, dict):
            policy = {}
        items.append(
            {
                "id": row["id"],
                "key": row["key"],
                "enabled": bool(row["enabled"]),
                "policy": policy,
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
        )
    return items
