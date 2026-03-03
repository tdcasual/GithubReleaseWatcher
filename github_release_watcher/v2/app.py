from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

from .db import init_db
from .jobs import enqueue_job, list_jobs


class EnqueueJobRequest(BaseModel):
    kind: str
    payload: dict[str, Any] = Field(default_factory=dict)


def create_app(*, db_path: Path | None = None) -> FastAPI:
    resolved_db_path = Path(db_path) if db_path is not None else Path("./v2.sqlite3")
    init_db(resolved_db_path)
    app = FastAPI(title="GitHub Release Watcher V2")

    @app.get("/api/v2/health")
    def health() -> dict[str, object]:
        return {"ok": True, "api_version": "v2"}

    @app.post("/api/v2/jobs", status_code=201)
    def post_jobs(body: EnqueueJobRequest) -> dict[str, Any]:
        return enqueue_job(
            resolved_db_path,
            kind=body.kind,
            payload=body.payload,
        )

    @app.get("/api/v2/jobs")
    def get_jobs(limit: int = 100) -> dict[str, list[dict[str, Any]]]:
        return {"items": list_jobs(resolved_db_path, limit=limit)}

    return app
