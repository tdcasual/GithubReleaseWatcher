from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from .config import AppConfig, RepoConfig
from .state import load_state


class RepoQueryService:
    def __init__(
        self,
        *,
        repo_key_from_spec: Callable[[str], str],
        recommended_interval_seconds: Callable[[AppConfig, dict[str, Any]], int | None],
    ) -> None:
        self._repo_key_from_spec = repo_key_from_spec
        self._recommended_interval_seconds = recommended_interval_seconds

    @staticmethod
    def _repos_state(config: AppConfig, state: dict[str, Any] | None) -> dict[str, Any]:
        source = state if isinstance(state, dict) else load_state(config.state_file)
        return source.get("repos", {}) if isinstance(source.get("repos"), dict) else {}

    def list_repo_summaries(
        self,
        *,
        config: AppConfig,
        next_runs: dict[str, float],
        scheduler_enabled: bool,
        state: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        repos_state = self._repos_state(config, state)

        items: list[dict[str, Any]] = []
        for repo_cfg in config.repos:
            try:
                key = self._repo_key_from_spec(repo_cfg.name)
            except Exception:
                key = repo_cfg.name
            repo_state = repos_state.get(key, {}) if isinstance(repos_state.get(key), dict) else {}
            stats = repo_state.get("stats", {}) if isinstance(repo_state.get("stats"), dict) else {}
            update = repo_state.get("update", {}) if isinstance(repo_state.get("update"), dict) else {}
            releases = repo_state.get("releases", {}) if isinstance(repo_state.get("releases"), dict) else {}

            downloaded_releases = 0
            for entry in releases.values():
                if not isinstance(entry, dict):
                    continue
                assets = entry.get("downloaded_assets", [])
                if isinstance(assets, list) and assets:
                    downloaded_releases += 1

            next_run_at = next_runs.get(key) if scheduler_enabled else None
            items.append(
                {
                    "key": key,
                    "enabled": bool(getattr(repo_cfg, "enabled", True)),
                    "name": repo_cfg.name,
                    "keep_last": repo_cfg.keep_last,
                    "keep_last_effective": (repo_cfg.keep_last or config.keep_last),
                    "asset_types": list(getattr(repo_cfg, "asset_types", []) or []),
                    "include_prereleases": bool(repo_cfg.include_prereleases),
                    "include_drafts": bool(repo_cfg.include_drafts),
                    "stats": stats,
                    "update": update,
                    "downloaded_releases_total": downloaded_releases,
                    "next_run_at": datetime.fromtimestamp(next_run_at, tz=timezone.utc).isoformat() if next_run_at else None,
                    "recommended_interval_seconds": self._recommended_interval_seconds(config, repo_state),
                }
            )

        return items

    def get_repo_summary(
        self,
        *,
        config: AppConfig,
        repo_key: str,
        next_run_at: float | None,
        state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        repo_key = str(repo_key or "").strip()
        if not repo_key:
            raise ValueError("repo_key required")

        repos_state = self._repos_state(config, state)
        repo_state = repos_state.get(repo_key, {}) if isinstance(repos_state.get(repo_key), dict) else {}
        stats = repo_state.get("stats", {}) if isinstance(repo_state.get("stats"), dict) else {}
        update = repo_state.get("update", {}) if isinstance(repo_state.get("update"), dict) else {}
        releases = repo_state.get("releases", {}) if isinstance(repo_state.get("releases"), dict) else {}

        downloaded_releases = 0
        for entry in releases.values():
            if not isinstance(entry, dict):
                continue
            assets = entry.get("downloaded_assets", [])
            if isinstance(assets, list) and assets:
                downloaded_releases += 1

        cfg_repo: RepoConfig | None = None
        for repo_cfg in config.repos:
            try:
                key = self._repo_key_from_spec(repo_cfg.name)
            except Exception:
                key = repo_cfg.name
            if key == repo_key:
                cfg_repo = repo_cfg
                break
        if cfg_repo is None:
            raise ValueError("unknown repo")

        return {
            "key": repo_key,
            "enabled": bool(getattr(cfg_repo, "enabled", True)),
            "name": cfg_repo.name,
            "keep_last": cfg_repo.keep_last,
            "keep_last_effective": (cfg_repo.keep_last or config.keep_last),
            "asset_types": list(getattr(cfg_repo, "asset_types", []) or []),
            "include_prereleases": bool(cfg_repo.include_prereleases),
            "include_drafts": bool(cfg_repo.include_drafts),
            "stats": stats,
            "update": update,
            "downloaded_releases_total": downloaded_releases,
            "next_run_at": datetime.fromtimestamp(next_run_at, tz=timezone.utc).isoformat() if next_run_at else None,
            "recommended_interval_seconds": self._recommended_interval_seconds(config, repo_state),
        }

    def get_repo_activity(
        self,
        *,
        config: AppConfig,
        repo_key: str,
        limit: int = 200,
        state: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        repo_key = str(repo_key or "").strip()
        if not repo_key:
            raise ValueError("repo_key required")
        limit = max(1, min(int(limit), 2000))

        repos_state = self._repos_state(config, state)
        repo_state = repos_state.get(repo_key, {}) if isinstance(repos_state.get(repo_key), dict) else {}
        items = repo_state.get("activity", []) if isinstance(repo_state.get("activity"), list) else []
        tail = items[-limit:]
        return [x for x in tail if isinstance(x, dict)]

    def get_repo_releases(
        self,
        *,
        config: AppConfig,
        repo_key: str,
        limit: int = 100,
        state: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        repo_key = str(repo_key or "").strip()
        if not repo_key:
            raise ValueError("repo_key required")
        limit = max(1, min(int(limit), 2000))

        known = False
        for repo_cfg in config.repos:
            try:
                key = self._repo_key_from_spec(repo_cfg.name)
            except Exception:
                key = repo_cfg.name
            if key == repo_key:
                known = True
                break
        if not known:
            raise ValueError("unknown repo")

        repos_state = self._repos_state(config, state)
        repo_state = repos_state.get(repo_key, {}) if isinstance(repos_state.get(repo_key), dict) else {}
        releases = repo_state.get("releases", {}) if isinstance(repo_state.get("releases"), dict) else {}

        def parse_ts(raw: Any) -> datetime | None:
            if not isinstance(raw, str) or not raw.strip():
                return None
            try:
                dt = datetime.fromisoformat(raw)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except Exception:
                return None

        items: list[dict[str, Any]] = []
        for tag, entry in releases.items():
            if not isinstance(tag, str) or not tag:
                continue
            if not isinstance(entry, dict):
                entry = {}
            assets = entry.get("downloaded_assets", [])
            assets_list = assets if isinstance(assets, list) else []
            items.append(
                {
                    "tag": tag,
                    "processed_at": entry.get("processed_at"),
                    "published_at": entry.get("published_at"),
                    "created_at": entry.get("created_at"),
                    "html_url": entry.get("html_url"),
                    "downloaded_assets": [x for x in assets_list if isinstance(x, str)],
                    "downloaded_assets_count": len([x for x in assets_list if isinstance(x, str)]),
                    "_sort_ts": parse_ts(entry.get("published_at"))
                    or parse_ts(entry.get("created_at"))
                    or parse_ts(entry.get("processed_at"))
                    or datetime.min.replace(tzinfo=timezone.utc),
                }
            )

        items.sort(key=lambda x: x.get("_sort_ts") or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        for x in items:
            x.pop("_sort_ts", None)
        return items[:limit]
