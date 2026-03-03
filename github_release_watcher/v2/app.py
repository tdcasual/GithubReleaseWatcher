from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .auth import V2AuthService
from .db import init_db
from .jobs import append_event, enqueue_job, list_events, list_jobs


class EnqueueJobRequest(BaseModel):
    kind: str
    payload: dict[str, Any] = Field(default_factory=dict)


class LoginRequest(BaseModel):
    username: str
    password: str


class AppendEventRequest(BaseModel):
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)


def create_app(
    *,
    db_path: Path | None = None,
    auth_username: str = "admin",
    auth_password: str = "admin",
) -> FastAPI:
    resolved_db_path = Path(db_path) if db_path is not None else Path("./v2.sqlite3")
    init_db(resolved_db_path)
    auth_service = V2AuthService(username=auth_username, password=auth_password)
    app = FastAPI(title="GitHub Release Watcher V2")

    def _require_auth(request: Request) -> None:
        token = request.cookies.get("grw_v2_session")
        if not auth_service.is_valid(token):
            raise HTTPException(status_code=401, detail="unauthorized")

    @app.get("/api/v2/health")
    def health() -> dict[str, object]:
        return {"ok": True, "api_version": "v2"}

    @app.post("/api/v2/auth/login")
    def post_login(body: LoginRequest) -> JSONResponse:
        token = auth_service.login(username=body.username, password=body.password)
        if token is None:
            return JSONResponse({"error": "invalid_credentials"}, status_code=401)
        response = JSONResponse({"ok": True, "user": {"username": auth_service.username}})
        response.set_cookie(
            key="grw_v2_session",
            value=token,
            httponly=True,
            samesite="lax",
            path="/",
        )
        return response

    @app.post("/api/v2/auth/logout")
    def post_logout(request: Request) -> JSONResponse:
        token = request.cookies.get("grw_v2_session")
        auth_service.delete_session(token)
        response = JSONResponse({"ok": True})
        response.delete_cookie("grw_v2_session", path="/")
        return response

    @app.post("/api/v2/jobs", status_code=201)
    def post_jobs(body: EnqueueJobRequest, request: Request) -> dict[str, Any]:
        _require_auth(request)
        return enqueue_job(
            resolved_db_path,
            kind=body.kind,
            payload=body.payload,
        )

    @app.get("/api/v2/jobs")
    def get_jobs(request: Request, limit: int = 100) -> dict[str, list[dict[str, Any]]]:
        _require_auth(request)
        return {"items": list_jobs(resolved_db_path, limit=limit)}

    @app.post("/api/v2/jobs/{job_id}/events", status_code=201)
    def post_job_event(job_id: str, body: AppendEventRequest, request: Request) -> dict[str, Any]:
        _require_auth(request)
        try:
            return append_event(
                resolved_db_path,
                job_id=job_id,
                event_type=body.event_type,
                payload=body.payload,
            )
        except ValueError as exc:
            msg = str(exc)
            if msg == "job not found":
                raise HTTPException(status_code=404, detail=msg) from exc
            raise HTTPException(status_code=400, detail=msg) from exc

    @app.get("/api/v2/events")
    def get_events(request: Request, job_id: Optional[str] = None, limit: int = 100) -> dict[str, list[dict[str, Any]]]:
        _require_auth(request)
        return {"items": list_events(resolved_db_path, job_id=job_id, limit=limit)}

    return app
