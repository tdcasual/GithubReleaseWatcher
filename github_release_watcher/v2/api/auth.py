from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .common import get_ctx

router = APIRouter(prefix="/api/v2/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def post_login(body: LoginRequest, request: Request) -> JSONResponse:
    ctx = get_ctx(request)
    token = ctx.auth_service.login(username=body.username, password=body.password)
    if token is None:
        return JSONResponse({"error": "invalid_credentials"}, status_code=401)
    response = JSONResponse({"ok": True, "user": {"username": ctx.auth_service.username}})
    response.set_cookie(
        key="grw_v2_session",
        value=token,
        httponly=True,
        samesite="lax",
        path="/",
        secure=bool(ctx.session_cookie_secure),
    )
    return response


@router.post("/logout")
def post_logout(request: Request) -> JSONResponse:
    ctx = get_ctx(request)
    token = request.cookies.get("grw_v2_session")
    ctx.auth_service.delete_session(token)
    response = JSONResponse({"ok": True})
    response.delete_cookie("grw_v2_session", path="/")
    return response
