from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..db import connect_db


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def upsert_settings(*, db_path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    now = _now_iso()
    value_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    conn = connect_db(db_path)
    try:
        conn.execute(
            """
            INSERT INTO app_settings(key, value_json, updated_at)
            VALUES ('global', ?, ?)
            ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json, updated_at = excluded.updated_at
            """,
            (value_json, now),
        )
        conn.commit()
    finally:
        conn.close()
    return {"settings": payload, "updated_at": now}


def get_settings(*, db_path: Path) -> dict[str, Any]:
    conn = connect_db(db_path)
    try:
        row = conn.execute("SELECT value_json, updated_at FROM app_settings WHERE key = 'global'").fetchone()
    finally:
        conn.close()
    if row is None:
        return {"settings": {}, "updated_at": None}

    try:
        payload = json.loads(row["value_json"]) if isinstance(row["value_json"], str) else {}
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    return {"settings": payload, "updated_at": row["updated_at"]}
