from __future__ import annotations

from fastapi import APIRouter, Request

from ..repositories.settings_repo import get_settings
from .common import require_auth

router = APIRouter(prefix="/api/v2/storage", tags=["storage"])


@router.get("/health")
def get_storage_health(request: Request) -> dict[str, object]:
    ctx = require_auth(request)
    settings = get_settings(db_path=ctx.db_path).get("settings", {})
    mode = "local"
    if isinstance(settings, dict):
        mode = str(settings.get("storage", {}).get("mode") or "local") if isinstance(settings.get("storage"), dict) else "local"
    return {
        "mode": mode,
        "totals": {
            "upload_retry_total": 0,
            "upload_verify_failed_total": 0,
            "upload_queue_depth": 0,
        },
        "repos": [],
    }
