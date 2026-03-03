from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..jobs import enqueue_job, list_jobs
from .common import require_auth

router = APIRouter(prefix="/api/v2/jobs", tags=["jobs"])


class EnqueueJobRequest(BaseModel):
    kind: str
    payload: dict[str, Any] = Field(default_factory=dict)


@router.post("", status_code=201)
def post_jobs(body: EnqueueJobRequest, request: Request) -> dict[str, Any]:
    ctx = require_auth(request)
    try:
        return enqueue_job(ctx.db_path, kind=body.kind, payload=body.payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("")
def get_jobs(request: Request, limit: int = 100) -> dict[str, list[dict[str, Any]]]:
    ctx = require_auth(request)
    return {"items": list_jobs(ctx.db_path, limit=limit)}
