from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..jobs import append_event, list_events
from .common import require_auth

router = APIRouter(prefix="/api/v2", tags=["events"])


class AppendEventRequest(BaseModel):
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)


@router.post("/jobs/{job_id}/events", status_code=201)
def post_job_event(job_id: str, body: AppendEventRequest, request: Request) -> dict[str, Any]:
    ctx = require_auth(request)
    try:
        return append_event(
            ctx.db_path,
            job_id=job_id,
            event_type=body.event_type,
            payload=body.payload,
        )
    except ValueError as exc:
        msg = str(exc)
        if msg == "job not found":
            raise HTTPException(status_code=404, detail=msg) from exc
        raise HTTPException(status_code=400, detail=msg) from exc


@router.get("/events")
def get_events(request: Request, job_id: Optional[str] = None, limit: int = 100) -> dict[str, list[dict[str, Any]]]:
    ctx = require_auth(request)
    return {"items": list_events(ctx.db_path, job_id=job_id, limit=limit)}
