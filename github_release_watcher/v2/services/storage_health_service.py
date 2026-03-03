from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from ..repositories.settings_repo import get_settings


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _default_totals() -> dict[str, int]:
    return {
        "upload_retry_total": 0,
        "upload_verify_failed_total": 0,
        "upload_queue_depth": 0,
    }


class StorageHealthProvider(Protocol):
    def collect(self, *, mode: str, settings: dict[str, Any]) -> dict[str, Any]:
        ...


@dataclass
class DefaultStorageHealthProvider:
    def collect(self, *, mode: str, settings: dict[str, Any]) -> dict[str, Any]:
        totals = _default_totals()
        repos: list[dict[str, Any]] = []

        storage = settings.get("storage") if isinstance(settings, dict) else {}
        if not isinstance(storage, dict):
            storage = {}

        if mode == "webdav":
            webdav = storage.get("webdav")
            if isinstance(webdav, dict) and str(webdav.get("base_url") or "").strip():
                repos.append({"kind": "webdav", "configured": True})
            else:
                repos.append({"kind": "webdav", "configured": False})

        return {"totals": totals, "repos": repos}


class StorageHealthService:
    def __init__(self, *, db_path: Path, provider: StorageHealthProvider | None = None) -> None:
        self._db_path = Path(db_path)
        self._provider = provider or DefaultStorageHealthProvider()

    def get_health(self) -> dict[str, object]:
        settings_doc = get_settings(db_path=self._db_path)
        settings = settings_doc.get("settings", {})
        settings_payload = settings if isinstance(settings, dict) else {}
        updated_at = settings_doc.get("updated_at")

        mode = "local"
        storage = settings_payload.get("storage")
        if isinstance(storage, dict):
            mode = str(storage.get("mode") or "local").strip().lower() or "local"

        provider_payload = self._provider.collect(mode=mode, settings=settings_payload)
        totals = provider_payload.get("totals")
        repos = provider_payload.get("repos")
        if not isinstance(totals, dict):
            totals = _default_totals()
        if not isinstance(repos, list):
            repos = []

        return {
            "mode": mode,
            "totals": totals,
            "repos": repos,
            "source": "storage_health_service",
            "checked_at": _now_iso(),
            "settings_updated_at": updated_at if isinstance(updated_at, str) else None,
        }
