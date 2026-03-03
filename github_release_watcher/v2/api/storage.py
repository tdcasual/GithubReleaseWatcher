from __future__ import annotations

from fastapi import APIRouter, Request

from ..services.storage_health_service import StorageHealthService
from .common import require_auth

router = APIRouter(prefix="/api/v2/storage", tags=["storage"])


@router.get("/health")
def get_storage_health(request: Request) -> dict[str, object]:
    ctx = require_auth(request)
    return StorageHealthService(db_path=ctx.db_path).get_health()
