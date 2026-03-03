from __future__ import annotations

from pathlib import Path
from typing import Any

from .services.jobs_service import JobsService


def enqueue_job(db_path: Path, *, kind: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return JobsService(db_path).enqueue_job(kind=kind, payload=payload)


def list_jobs(db_path: Path, *, limit: int = 100) -> list[dict[str, Any]]:
    return JobsService(db_path).list_jobs(limit=limit)


def append_event(
    db_path: Path,
    *,
    job_id: str,
    event_type: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return JobsService(db_path).append_event(job_id=job_id, event_type=event_type, payload=payload)


def list_events(db_path: Path, *, job_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    return JobsService(db_path).list_events(job_id=job_id, limit=limit)
