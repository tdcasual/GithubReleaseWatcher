from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..db import connect_db
from ..domain.job_state import assert_transition, target_status_for_event
from ..repositories import events_repo, jobs_repo


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _decode_payload(raw: Any) -> dict[str, Any]:
    try:
        data = json.loads(raw) if isinstance(raw, str) else {}
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return data


class JobsService:
    def __init__(self, db_path: Path) -> None:
        self._db_path = Path(db_path)

    def enqueue_job(self, *, kind: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        kind_value = str(kind or "").strip()
        if not kind_value:
            raise ValueError("kind is required")

        job_id = uuid.uuid4().hex
        created_at = _now_iso()
        payload_dict = payload or {}
        payload_json = json.dumps(payload_dict, ensure_ascii=False, sort_keys=True)

        conn = connect_db(self._db_path)
        try:
            jobs_repo.insert_job(
                conn,
                job_id=job_id,
                kind=kind_value,
                payload_json=payload_json,
                created_at=created_at,
            )
            conn.commit()
        finally:
            conn.close()

        return {
            "id": job_id,
            "kind": kind_value,
            "status": "queued",
            "payload": payload_dict,
            "created_at": created_at,
            "updated_at": created_at,
        }

    def list_jobs(self, *, limit: int = 100) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 1000))
        conn = connect_db(self._db_path)
        try:
            rows = jobs_repo.list_jobs(conn, limit=safe_limit)
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
        self,
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

        conn = connect_db(self._db_path)
        try:
            job = jobs_repo.get_job(conn, job_id=job_id_value)
            if job is None:
                raise ValueError("job not found")

            event_id = events_repo.insert_event(
                conn,
                job_id=job_id_value,
                event_type=event_type_value,
                payload_json=payload_json,
                created_at=created_at,
            )

            target_status = target_status_for_event(event_type_value)
            if target_status is not None:
                current_status = str(job["status"])
                assert_transition(current_status, target_status)
                error_text = str(payload_dict.get("error_text") or "") if target_status == "failed" else None
                jobs_repo.update_job_status(
                    conn,
                    job_id=job_id_value,
                    status=target_status,
                    updated_at=created_at,
                    error_text=error_text,
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

    def list_events(self, *, job_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 1000))
        conn = connect_db(self._db_path)
        try:
            rows = events_repo.list_events(conn, job_id=job_id, limit=safe_limit)
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
