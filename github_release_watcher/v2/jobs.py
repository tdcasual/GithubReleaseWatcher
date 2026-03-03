from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .db import connect_db


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "queued": {"running", "canceled"},
    "running": {"succeeded", "failed", "canceled"},
    "succeeded": set(),
    "failed": set(),
    "canceled": set(),
}


_EVENT_TO_STATUS = {
    "started": "running",
    "job_started": "running",
    "succeeded": "succeeded",
    "job_succeeded": "succeeded",
    "failed": "failed",
    "job_failed": "failed",
    "canceled": "canceled",
    "job_canceled": "canceled",
}


def _decode_payload(raw: Any) -> dict[str, Any]:
    try:
        data = json.loads(raw) if isinstance(raw, str) else {}
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def _assert_transition(current: str, nxt: str) -> None:
    if nxt not in _STATUS_TRANSITIONS.get(current, set()):
        raise ValueError(f"invalid transition: {current}->{nxt}")


def enqueue_job(db_path: Path, *, kind: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    job_id = uuid.uuid4().hex
    created_at = _now_iso()
    payload_json = json.dumps(payload or {}, ensure_ascii=False, sort_keys=True)
    kind_value = str(kind or "").strip()
    if not kind_value:
        raise ValueError("kind is required")

    conn = connect_db(db_path)
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
    conn = connect_db(db_path)
    try:
        rows = conn.execute(
            "SELECT id, kind, status, payload_json, created_at, updated_at, error_text FROM jobs ORDER BY created_at DESC, id DESC LIMIT ?",
            (safe_limit,),
        ).fetchall()
    finally:
        conn.close()

    return [
        {
            "id": row["id"],
            "kind": row["kind"],
            "status": row["status"],
            "payload": _decode_payload(row["payload_json"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "error_text": row["error_text"],
        }
        for row in rows
    ]


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

    payload_dict = payload or {}
    payload_json = json.dumps(payload_dict, ensure_ascii=False, sort_keys=True)
    created_at = _now_iso()

    conn = connect_db(db_path)
    try:
        job = conn.execute("SELECT id, status FROM jobs WHERE id = ?", (job_id_value,)).fetchone()
        if job is None:
            raise ValueError("job not found")

        conn.execute(
            "INSERT INTO events(job_id, event_type, payload_json, created_at) VALUES (?, ?, ?, ?)",
            (job_id_value, event_type_value, payload_json, created_at),
        )
        event_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])

        target_status = _EVENT_TO_STATUS.get(event_type_value)
        if target_status is not None:
            current_status = str(job["status"])
            _assert_transition(current_status, target_status)
            error_text = str(payload_dict.get("error_text") or "") if target_status == "failed" else None
            conn.execute(
                "UPDATE jobs SET status = ?, updated_at = ?, error_text = ? WHERE id = ?",
                (target_status, created_at, error_text, job_id_value),
            )

        conn.commit()
    finally:
        conn.close()

    return {
        "id": event_id,
        "job_id": job_id_value,
        "event_type": event_type_value,
        "payload": payload_dict,
        "created_at": created_at,
    }


def list_events(db_path: Path, *, job_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit), 1000))
    conn = connect_db(db_path)
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
