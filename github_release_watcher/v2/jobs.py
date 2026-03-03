from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def enqueue_job(db_path: Path, *, kind: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    job_id = uuid.uuid4().hex
    created_at = _now_iso()
    payload_json = json.dumps(payload or {}, ensure_ascii=False, sort_keys=True)
    kind_value = str(kind or "").strip()
    if not kind_value:
        raise ValueError("kind is required")

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO jobs(id, kind, status, payload_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (job_id, kind_value, "queued", payload_json, created_at, created_at),
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "id": job_id,
        "kind": kind_value,
        "status": "queued",
        "payload": payload or {},
        "created_at": created_at,
        "updated_at": created_at,
    }


def list_jobs(db_path: Path, *, limit: int = 100) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit), 1000))
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT id, kind, status, payload_json, created_at, updated_at, error_text FROM jobs ORDER BY created_at DESC, id DESC LIMIT ?",
            (safe_limit,),
        ).fetchall()
    finally:
        conn.close()

    items: list[dict[str, Any]] = []
    for row in rows:
        payload = row["payload_json"]
        try:
            payload_dict = json.loads(payload) if isinstance(payload, str) else {}
        except Exception:
            payload_dict = {}
        if not isinstance(payload_dict, dict):
            payload_dict = {}

        items.append(
            {
                "id": row["id"],
                "kind": row["kind"],
                "status": row["status"],
                "payload": payload_dict,
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "error_text": row["error_text"],
            }
        )
    return items

