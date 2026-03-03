from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..repositories.repos_repo import add_repo, list_repos
from .common import require_auth

router = APIRouter(prefix="/api/v2/repos", tags=["repos"])


class RepoCreateRequest(BaseModel):
    key: str
    enabled: bool = True
    policy: dict[str, Any] = Field(default_factory=dict)


@router.post("", status_code=201)
def post_repo(body: RepoCreateRequest, request: Request) -> dict[str, Any]:
    ctx = require_auth(request)
    key = str(body.key or "").strip()
    if not key or "/" not in key:
        raise HTTPException(status_code=400, detail="repo key must be owner/repo")
    return add_repo(db_path=ctx.db_path, key=key, enabled=bool(body.enabled), policy=body.policy)


@router.get("")
def get_repos(request: Request, limit: int = 500) -> dict[str, list[dict[str, Any]]]:
    ctx = require_auth(request)
    return {"items": list_repos(db_path=ctx.db_path, limit=limit)}
