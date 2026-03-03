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
        items.append(
            {
                "id": row["id"],
                "kind": row["kind"],
                "status": row["status"],
                "payload": _decode_payload(row["payload_json"]),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "error_text": row["error_text"],
            }
        )
    return items


def append_event(
    db_path: Path,
    *,
    job_id: str,
    event_type: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    job_id_value = str(job_id or "").strip()
    event_type_value = str(event_type or "").strip()
    if not job_id_value:
        raise ValueError("job_id is required")
    if not event_type_value:
        raise ValueError("event_type is required")
    payload_json = json.dumps(payload or {}, ensure_ascii=False, sort_keys=True)
    created_at = _now_iso()

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT id FROM jobs WHERE id = ?", (job_id_value,)).fetchone()
        if row is None:
            raise ValueError("job not found")

        conn.execute(
            "INSERT INTO events(job_id, event_type, payload_json, created_at) VALUES (?, ?, ?, ?)",
            (job_id_value, event_type_value, payload_json, created_at),
        )
        event_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.commit()
    finally:
        conn.close()

    return {
        "id": int(event_id),
        "job_id": job_id_value,
        "event_type": event_type_value,
        "payload": payload or {},
        "created_at": created_at,
    }


def list_events(db_path: Path, *, job_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit), 1000))
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        if isinstance(job_id, str) and job_id.strip():
            rows = conn.execute(
                """
                SELECT id, job_id, event_type, payload_json, created_at
                FROM events
                WHERE job_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (job_id.strip(), safe_limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, job_id, event_type, payload_json, created_at
                FROM events
                ORDER BY id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
    finally:
        conn.close()

    return [
        {
            "id": row["id"],
            "job_id": row["job_id"],
            "event_type": row["event_type"],
            "payload": _decode_payload(row["payload_json"]),
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def _decode_payload(raw: Any) -> dict[str, Any]:
    try:
        data = json.loads(raw) if isinstance(raw, str) else {}
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return data
