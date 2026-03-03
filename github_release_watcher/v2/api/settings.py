from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from ..repositories.settings_repo import get_settings, upsert_settings
from .common import require_auth

router = APIRouter(prefix="/api/v2/settings", tags=["settings"])


@router.get("")
def get_settings_route(request: Request) -> dict[str, Any]:
    ctx = require_auth(request)
    return get_settings(db_path=ctx.db_path)


@router.put("")
def put_settings_route(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    ctx = require_auth(request)
    return upsert_settings(db_path=ctx.db_path, payload=payload)
