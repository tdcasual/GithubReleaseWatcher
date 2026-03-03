from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from .api import auth_router, events_router, jobs_router, repos_router, settings_router, storage_router
from .api.common import AppContext
from .auth import V2AuthService
from .db import init_db


def create_app(
    *,
    db_path: Path | None = None,
    auth_username: str = "admin",
    auth_password: str = "admin",
) -> FastAPI:
    resolved_db_path = Path(db_path) if db_path is not None else Path("./v2.sqlite3")
    init_db(resolved_db_path)

    auth_service = V2AuthService(db_path=resolved_db_path, username=auth_username, password=auth_password)

    app = FastAPI(title="GitHub Release Watcher V2")
    app.state.ctx = AppContext(db_path=resolved_db_path, auth_service=auth_service)

    @app.get("/api/v2/health")
    def health() -> dict[str, object]:
        return {"ok": True, "api_version": "v2"}

    app.include_router(auth_router)
    app.include_router(jobs_router)
    app.include_router(events_router)
    app.include_router(repos_router)
    app.include_router(settings_router)
    app.include_router(storage_router)

    return app
