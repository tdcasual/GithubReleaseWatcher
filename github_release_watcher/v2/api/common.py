from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException, Request

from ..auth import V2AuthService


@dataclass
class AppContext:
    db_path: Path
    auth_service: V2AuthService
    session_cookie_secure: bool


def get_ctx(request: Request) -> AppContext:
    ctx = getattr(request.app.state, "ctx", None)
    if ctx is None:
        raise RuntimeError("app context not initialized")
    return ctx


def require_auth(request: Request) -> AppContext:
    ctx = get_ctx(request)
    token = request.cookies.get("grw_v2_session")
    if not ctx.auth_service.is_valid(token):
        raise HTTPException(status_code=401, detail="unauthorized")
    return ctx
