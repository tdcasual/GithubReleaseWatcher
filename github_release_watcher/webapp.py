from __future__ import annotations

import copy
import json
import logging
import queue
import random
import secrets
import threading
import time
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from .auth_service import AuthService, _default_auth_config, _load_auth_config, _pbkdf2_hash, _verify_password
from .config import AppConfig, ConfigError, RepoConfig, WebDAVConfig, load_config
from .github import parse_repo_spec
from .state import load_state
from .webapp_payloads import (
    _compile_regex_list,
    _normalize_asset_types,
    _normalize_storage_mode,
    _safe_int,
)
from .webapp_overrides import _apply_overrides, _repo_key_from_spec
from .watcher import run_once as watcher_run_once
from .webdav import WebDAVClient, WebDAVError


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _read_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "updated_at": _utc_now_iso(), "app": {}, "repos": {}, "auth": {}, "storage": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "updated_at": _utc_now_iso(), "app": {}, "repos": {}, "auth": {}, "storage": {}}
    if not isinstance(data, dict):
        return {"version": 1, "updated_at": _utc_now_iso(), "app": {}, "repos": {}, "auth": {}, "storage": {}}
    if data.get("version") != 1:
        return {"version": 1, "updated_at": _utc_now_iso(), "app": {}, "repos": {}, "auth": {}, "storage": {}}
    data.setdefault("app", {})
    data.setdefault("repos", {})
    data.setdefault("auth", {})
    data.setdefault("storage", {})
    if not isinstance(data["app"], dict):
        data["app"] = {}
    if not isinstance(data["repos"], dict):
        data["repos"] = {}
    if not isinstance(data["auth"], dict):
        data["auth"] = {}
    if not isinstance(data["storage"], dict):
        data["storage"] = {}
    return data


def _write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def _guess_asset_types_from_patterns(patterns: list[str]) -> list[str]:
    joined = " ".join(patterns).lower()
    guesses: list[str] = []
    for ext in ("exe", "apk", "zip", "tar.gz", "dmg", "deb", "rpm"):
        token = "." + ext.replace(".", r"\.")
        if token in joined or (ext == "tar.gz" and (".tar\\.gz" in joined or ".tar.gz" in joined)):
            guesses.append(ext)
    return guesses


def _sanitize_path_component(value: str) -> str:
    raw = str(value or "").strip()
    raw = raw.replace("/", "__").replace("\\", "__")
    raw = raw.replace("..", "__")
    return raw or "__empty__"


def _public_config(config: AppConfig) -> dict[str, Any]:
    repos: list[dict[str, Any]] = []
    for repo_cfg in config.repos:
        try:
            owner, repo, https_url = parse_repo_spec(repo_cfg.name)
            key = f"{owner}/{repo}"
        except Exception:
            key = repo_cfg.name
            https_url = None

        effective_keep_last = repo_cfg.keep_last or config.keep_last
        asset_types_effective = repo_cfg.asset_types or _guess_asset_types_from_patterns(repo_cfg.include_assets)

        repos.append(
            {
                "key": key,
                "name": repo_cfg.name,
                "repo_url": https_url,
                "enabled": bool(getattr(repo_cfg, "enabled", True)),
                "keep_last": repo_cfg.keep_last,
                "effective_keep_last": effective_keep_last,
                "asset_types": list(getattr(repo_cfg, "asset_types", [])),
                "asset_types_effective": asset_types_effective,
                "include_assets": list(repo_cfg.include_assets),
                "exclude_assets": list(repo_cfg.exclude_assets),
                "include_prereleases": bool(repo_cfg.include_prereleases),
                "include_drafts": bool(repo_cfg.include_drafts),
            }
        )

    return {
        "app": {
            "interval_seconds": config.interval_seconds,
            "download_dir": str(config.download_dir),
            "state_file": str(config.state_file),
            "keep_last": config.keep_last,
        },
        "github": {
            "api_base": config.github.api_base,
            "token_configured": bool(config.github.token),
        },
        "storage": {
            "mode": str(getattr(config, "storage_mode", "local") or "local"),
            "local_dir": str(config.download_dir),
            "webdav": {
                "base_url": str(getattr(getattr(config, "webdav", None), "base_url", "") or ""),
                "username": getattr(getattr(config, "webdav", None), "username", None),
                "verify_tls": bool(getattr(getattr(config, "webdav", None), "verify_tls", True)),
                "timeout_seconds": int(getattr(getattr(config, "webdav", None), "timeout_seconds", 60) or 60),
                "upload_concurrency": int(getattr(getattr(config, "webdav", None), "upload_concurrency", 2) or 2),
                "max_retries": int(getattr(getattr(config, "webdav", None), "max_retries", 3) or 3),
                "retry_backoff_seconds": int(getattr(getattr(config, "webdav", None), "retry_backoff_seconds", 2) or 2),
                "verify_after_upload": bool(getattr(getattr(config, "webdav", None), "verify_after_upload", True)),
                "upload_temp_suffix": str(getattr(getattr(config, "webdav", None), "upload_temp_suffix", ".uploading") or ".uploading"),
                "cleanup_mode": str(getattr(getattr(config, "webdav", None), "cleanup_mode", "delete") or "delete"),
            },
        },
        "repos": repos,
    }


class ActivityBuffer(logging.Handler):
    def __init__(self, capacity: int = 500):
        super().__init__(level=logging.NOTSET)
        self._lock = threading.Lock()
        self._capacity = max(50, int(capacity))
        self._items: list[dict[str, Any]] = []

    def emit(self, record: logging.LogRecord) -> None:
        if not record.name.startswith("github_release_watcher.activity"):
            return

        try:
            payload = {
                "time": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
                "level": record.levelname,
                "type": getattr(record, "event_type", None),
                "repo": getattr(record, "repo", None),
                "tag": getattr(record, "tag", None),
                "path": getattr(record, "path", None),
                "message": record.getMessage(),
            }
        except Exception:
            return

        with self._lock:
            self._items.append(payload)
            if len(self._items) > self._capacity:
                self._items = self._items[-self._capacity :]

    def snapshot(self, limit: int = 200) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), self._capacity))
        with self._lock:
            return list(self._items[-limit:])


class WatcherService:
    def __init__(self, config_path: Path, overrides_path: Path | None = None, log_file: Path | None = None):
        self._config_path = config_path
        self._overrides_path = overrides_path or config_path.with_name("config.override.json")
        self._log_file = log_file

        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._queue: queue.Queue[dict[str, Any]] = queue.Queue()

        self._scheduler_enabled = True
        self._next_run_at: float | None = None
        self._repo_next_run_at: dict[str, float] = {}
        self._rng = random.Random()

        self._run_requested = False
        self._run_in_progress = False
        self._run_id = 0

        self._started_at = _utc_now_iso()
        self._last_config_reload_at: str | None = None
        self._config_error: str | None = None
        self._config: AppConfig | None = None
        self._overrides: dict[str, Any] = {}
        self._auth_config: dict[str, Any] = _default_auth_config()

        self._last_run: dict[str, Any] | None = None

        self.reload_config()

        self._worker = threading.Thread(target=self._worker_loop, name="watcher-worker", daemon=True)
        self._scheduler = threading.Thread(target=self._scheduler_loop, name="watcher-scheduler", daemon=True)

    @property
    def overrides_path(self) -> Path:
        return self._overrides_path

    def start(self, *, scheduler_enabled: bool = True, run_immediately: bool = True) -> None:
        with self._lock:
            self._scheduler_enabled = bool(scheduler_enabled)
            if self._scheduler_enabled:
                self._init_repo_schedule_locked(run_immediately=run_immediately)
                self._refresh_global_next_run_at_locked()
            else:
                self._next_run_at = None

        self._worker.start()
        self._scheduler.start()

        if not scheduler_enabled and run_immediately:
            self.enqueue_run_once(source="startup")

    def shutdown(self) -> None:
        self._stop_event.set()
        try:
            self._worker.join(timeout=5)
        except Exception:
            pass
        try:
            self._scheduler.join(timeout=5)
        except Exception:
            pass

    def _interval_seconds(self, *, default: int) -> int:
        with self._lock:
            if self._config is None:
                return default
            return int(self._config.interval_seconds)

    def _enabled_repo_keys(self, config: AppConfig) -> list[str]:
        keys: list[str] = []
        for repo_cfg in config.repos:
            if not bool(getattr(repo_cfg, "enabled", True)):
                continue
            try:
                keys.append(_repo_key_from_spec(repo_cfg.name))
            except Exception:
                keys.append(repo_cfg.name)
        return keys

    def _refresh_global_next_run_at_locked(self) -> None:
        if not self._scheduler_enabled:
            self._next_run_at = None
            return
        if not self._repo_next_run_at:
            self._next_run_at = None
            return
        self._next_run_at = min(self._repo_next_run_at.values())

    def _init_repo_schedule_locked(self, *, run_immediately: bool) -> None:
        config = self._config
        self._repo_next_run_at.clear()
        if config is None:
            self._next_run_at = None
            return

        now = time.time()
        base = max(60, int(config.interval_seconds))
        for key in self._enabled_repo_keys(config):
            self._repo_next_run_at[key] = now if run_immediately else now + base

    def _sync_repo_schedule_locked(self) -> None:
        config = self._config
        if config is None:
            self._repo_next_run_at.clear()
            self._next_run_at = None
            return

        enabled_keys = set(self._enabled_repo_keys(config))
        now = time.time()
        for key in list(self._repo_next_run_at.keys()):
            if key not in enabled_keys:
                self._repo_next_run_at.pop(key, None)
        for key in enabled_keys:
            if key not in self._repo_next_run_at:
                self._repo_next_run_at[key] = now

        self._refresh_global_next_run_at_locked()

    def _recommended_interval_seconds(self, config: AppConfig, repo_state: dict[str, Any]) -> int:
        base = max(60, int(getattr(config, "interval_seconds", 172800) or 172800))
        update = repo_state.get("update", {}) if isinstance(repo_state.get("update"), dict) else {}
        median = update.get("median_interval_seconds")
        if isinstance(median, (int, float)) and float(median) > 0:
            return max(base, int(float(median) * 1.1))
        return base

    def _compute_next_repo_run_at(self, config: AppConfig, repo_state: dict[str, Any], *, now: float) -> float:
        interval = float(self._recommended_interval_seconds(config, repo_state))
        stats = repo_state.get("stats", {}) if isinstance(repo_state.get("stats"), dict) else {}
        ok = stats.get("last_check_ok")
        last_error_type = str(stats.get("last_error_type") or "")
        had_net = bool(stats.get("last_check_had_network_error", False))

        if ok is True:
            return now + interval

        if last_error_type == "network" or had_net:
            retry_seconds = float(self._rng.uniform(2 * 3600, 6 * 3600))
            return now + retry_seconds

        return now + interval

    def reload_config(self) -> None:
        with self._lock:
            self._config_error = None
            self._last_config_reload_at = _utc_now_iso()
            self._overrides = _read_json_file(self._overrides_path)
            self._auth_config = _load_auth_config(self._overrides)

            try:
                config = load_config(self._config_path)
            except ConfigError as exc:
                self._config = None
                self._config_error = str(exc)
                logging.error("Config error: %s", exc)
                return
            except Exception as exc:
                self._config = None
                self._config_error = f"Unexpected error while loading config: {exc}"
                logging.exception("Unexpected error while loading config")
                return

            try:
                _apply_overrides(config, self._overrides, base_dir=self._config_path.resolve().parent)
            except Exception as exc:
                self._config_error = f"Invalid overrides: {exc}"
                logging.exception("Failed applying overrides; continuing with base config")

            self._config = config
            self._sync_repo_schedule_locked()

    def auth_username(self) -> str:
        with self._lock:
            return str(self._auth_config.get("username") or "admin")

    def must_change_password(self) -> bool:
        with self._lock:
            return bool(self._auth_config.get("must_change_password", False))

    def verify_login(self, username: str, password: str) -> bool:
        with self._lock:
            if username.strip() != str(self._auth_config.get("username")):
                return False
            return _verify_password(password, self._auth_config)

    def set_credentials(self, username: str, password: str) -> None:
        username = username.strip()
        if not username:
            raise ValueError("username required")
        if len(username) > 64:
            raise ValueError("username too long")
        if len(password) < 1:
            raise ValueError("password required")

        overrides = _read_json_file(self._overrides_path)
        salt_hex = secrets.token_bytes(16).hex()
        iterations = 200_000
        overrides["auth"] = {
            "username": username,
            "salt": salt_hex,
            "iterations": iterations,
            "password_hash": _pbkdf2_hash(password, salt_hex=salt_hex, iterations=iterations),
            "must_change_password": False,
        }
        overrides["updated_at"] = _utc_now_iso()
        _write_json_atomic(self._overrides_path, overrides)
        self.reload_config()

    def enqueue_run_once(
        self,
        *,
        source: str = "manual",
        repo: str | None = None,
        repos: list[str] | None = None,
    ) -> bool:
        if repo is not None and repos is not None:
            raise ValueError("repo and repos cannot be set together")

        repo_key: str | None = None
        repo_keys: list[str] | None = None
        if repo is not None:
            if not isinstance(repo, str) or not repo.strip():
                raise ValueError("repo must be a non-empty string")
            repo_key = _repo_key_from_spec(repo)
        if repos is not None:
            if not isinstance(repos, list) or not repos:
                raise ValueError("repos must be a non-empty list")
            normalized: list[str] = []
            for item in repos:
                if not isinstance(item, str) or not item.strip():
                    raise ValueError("repos items must be non-empty strings")
                key = _repo_key_from_spec(item)
                if key not in normalized:
                    normalized.append(key)
            repo_keys = normalized

        with self._lock:
            if repo_key is not None or repo_keys is not None:
                config = self._config
                if config is None:
                    raise RuntimeError("Config not loaded")
                existing = set()
                for repo_cfg in config.repos:
                    try:
                        existing.add(_repo_key_from_spec(repo_cfg.name))
                    except Exception:
                        existing.add(repo_cfg.name)
                if repo_key is not None and repo_key not in existing:
                    raise ValueError("unknown repo")
                if repo_keys is not None:
                    for key in repo_keys:
                        if key not in existing:
                            raise ValueError("unknown repo")

            if self._run_requested or self._run_in_progress:
                return False
            self._run_requested = True
            task: dict[str, Any] = {"type": "run_once"}
            if repo_keys is not None:
                task["repo_keys"] = list(repo_keys)
            else:
                task["repo_key"] = repo_key
            self._queue.put(task)
            self._last_run = {
                "id": self._run_id + 1,
                "source": source,
                "repo": repo_key,
                "repos": list(repo_keys) if repo_keys is not None else None,
                "queued_at": _utc_now_iso(),
                "started_at": None,
                "finished_at": None,
                "exit_code": None,
                "error": None,
            }
            return True

    def set_scheduler(self, enabled: bool) -> None:
        with self._lock:
            self._scheduler_enabled = bool(enabled)
            if self._scheduler_enabled:
                if not self._repo_next_run_at:
                    self._init_repo_schedule_locked(run_immediately=True)
                self._refresh_global_next_run_at_locked()
            else:
                self._next_run_at = None

    def update_settings(self, payload: dict[str, Any]) -> None:
        overrides = _read_json_file(self._overrides_path)

        auth_patch = payload.get("auth", {}) if isinstance(payload.get("auth"), dict) else {}
        if auth_patch:
            username = auth_patch.get("username")
            password = auth_patch.get("password")
            if isinstance(username, str) and isinstance(password, str):
                # Reuse set_credentials to validate & persist.
                self.set_credentials(username, password)
                overrides = _read_json_file(self._overrides_path)

        app_patch = payload.get("app", {}) if isinstance(payload.get("app"), dict) else {}
        if "keep_last" in app_patch:
            overrides.setdefault("app", {})["keep_last"] = _safe_int(app_patch["keep_last"], min_value=1, max_value=1000)
        if "interval_seconds" in app_patch:
            overrides.setdefault("app", {})["interval_seconds"] = _safe_int(
                app_patch["interval_seconds"], min_value=1, max_value=31_536_000
            )

        storage_patch = payload.get("storage", {}) if isinstance(payload.get("storage"), dict) else {}
        if storage_patch:
            storage_store = overrides.setdefault("storage", {})
            if not isinstance(storage_store, dict):
                storage_store = {}
                overrides["storage"] = storage_store

            if "mode" in storage_patch:
                storage_store["mode"] = _normalize_storage_mode(storage_patch.get("mode"))

            if "local_dir" in storage_patch:
                raw = storage_patch.get("local_dir")
                if raw is None:
                    storage_store.pop("local_dir", None)
                elif isinstance(raw, str) and raw.strip():
                    storage_store["local_dir"] = raw.strip()
                else:
                    raise ValueError("storage.local_dir must be a non-empty string or null")

            webdav_patch = storage_patch.get("webdav", {}) if isinstance(storage_patch.get("webdav"), dict) else {}
            if "webdav" in storage_patch:
                webdav_store = storage_store.setdefault("webdav", {})
                if not isinstance(webdav_store, dict):
                    webdav_store = {}
                    storage_store["webdav"] = webdav_store

                if "base_url" in webdav_patch:
                    webdav_store["base_url"] = str(webdav_patch.get("base_url") or "").strip()
                if "username" in webdav_patch:
                    raw_user = webdav_patch.get("username")
                    webdav_store["username"] = str(raw_user).strip() if isinstance(raw_user, str) and raw_user.strip() else None
                if "password" in webdav_patch:
                    raw_pass = webdav_patch.get("password")
                    if raw_pass is None:
                        webdav_store.pop("password", None)
                    elif isinstance(raw_pass, str):
                        if raw_pass != "":
                            webdav_store["password"] = raw_pass
                    else:
                        raise ValueError("webdav.password must be a string or null")
                if "verify_tls" in webdav_patch:
                    webdav_store["verify_tls"] = bool(webdav_patch.get("verify_tls", True))
                if "timeout_seconds" in webdav_patch:
                    webdav_store["timeout_seconds"] = _safe_int(
                        webdav_patch.get("timeout_seconds"), min_value=5, max_value=600
                    )
                if "upload_concurrency" in webdav_patch:
                    webdav_store["upload_concurrency"] = _safe_int(
                        webdav_patch.get("upload_concurrency"), min_value=1, max_value=32
                    )
                if "max_retries" in webdav_patch:
                    webdav_store["max_retries"] = _safe_int(webdav_patch.get("max_retries"), min_value=1, max_value=20)
                if "retry_backoff_seconds" in webdav_patch:
                    webdav_store["retry_backoff_seconds"] = _safe_int(
                        webdav_patch.get("retry_backoff_seconds"), min_value=1, max_value=300
                    )
                if "verify_after_upload" in webdav_patch:
                    webdav_store["verify_after_upload"] = bool(webdav_patch.get("verify_after_upload", True))
                if "upload_temp_suffix" in webdav_patch:
                    suffix = str(webdav_patch.get("upload_temp_suffix") or "").strip()
                    if not suffix:
                        raise ValueError("webdav.upload_temp_suffix must be a non-empty string")
                    if "/" in suffix or "\\" in suffix:
                        raise ValueError("webdav.upload_temp_suffix cannot contain path separators")
                    webdav_store["upload_temp_suffix"] = suffix
                if "cleanup_mode" in webdav_patch:
                    cleanup_mode = str(webdav_patch.get("cleanup_mode") or "").strip().lower()
                    if cleanup_mode not in ("delete", "trash"):
                        raise ValueError("webdav.cleanup_mode must be 'delete' or 'trash'")
                    webdav_store["cleanup_mode"] = cleanup_mode

            mode_effective = _normalize_storage_mode(storage_store.get("mode"))
            if mode_effective == "webdav":
                webdav_store = storage_store.get("webdav", {})
                if not isinstance(webdav_store, dict):
                    raise ValueError("storage.webdav must be an object")
                base_url = str(webdav_store.get("base_url") or "").strip()
                if not base_url:
                    raise ValueError("webdav.base_url is required when storage.mode = 'webdav'")

        repos_patch = payload.get("repos", {}) if isinstance(payload.get("repos"), dict) else {}
        if repos_patch:
            repos_store = overrides.setdefault("repos", {})
            if not isinstance(repos_store, dict):
                repos_store = {}
                overrides["repos"] = repos_store

            for key, patch in repos_patch.items():
                if not isinstance(patch, dict):
                    continue
                spec = str(patch.get("name") or key)
                normalized_key = _repo_key_from_spec(spec)

                current = repos_store.get(normalized_key, {}) if isinstance(repos_store.get(normalized_key), dict) else {}
                updated = dict(current)
                updated["name"] = spec

                if "enabled" in patch:
                    updated["enabled"] = bool(patch["enabled"])
                if "keep_last" in patch:
                    raw_keep_last = patch["keep_last"]
                    updated["keep_last"] = None if raw_keep_last is None else _safe_int(raw_keep_last, min_value=1, max_value=1000)
                if "asset_types" in patch:
                    updated["asset_types"] = _normalize_asset_types(patch["asset_types"])
                if "include_assets" in patch:
                    updated["include_assets"] = _compile_regex_list(patch["include_assets"], "include_assets")
                if "exclude_assets" in patch:
                    updated["exclude_assets"] = _compile_regex_list(patch["exclude_assets"], "exclude_assets")
                if "include_prereleases" in patch:
                    updated["include_prereleases"] = bool(patch["include_prereleases"])
                if "include_drafts" in patch:
                    updated["include_drafts"] = bool(patch["include_drafts"])

                repos_store[normalized_key] = updated

        overrides["updated_at"] = _utc_now_iso()
        _write_json_atomic(self._overrides_path, overrides)

        self.reload_config()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            config = self._config
            next_run_at = (
                min(self._repo_next_run_at.values()) if self._scheduler_enabled and self._repo_next_run_at else None
            )
            base_interval_seconds = int(config.interval_seconds) if config is not None else None
            return {
                "started_at": self._started_at,
                "config_path": str(self._config_path),
                "overrides_path": str(self._overrides_path),
                "log_file": str(self._log_file) if self._log_file else None,
                "auth": {"username": str(self._auth_config.get("username") or "admin")},
                "security": {"must_change_password": bool(self._auth_config.get("must_change_password", False))},
                "config_loaded": config is not None,
                "config_error": self._config_error,
                "last_config_reload_at": self._last_config_reload_at,
                "scheduler": {
                    "enabled": self._scheduler_enabled,
                    "next_run_at": datetime.fromtimestamp(next_run_at, tz=timezone.utc).isoformat() if next_run_at else None,
                    "mode": "adaptive_per_repo",
                    "base_interval_seconds": base_interval_seconds,
                    "repos_scheduled": len(self._repo_next_run_at),
                },
                "run": {
                    "requested": self._run_requested,
                    "in_progress": self._run_in_progress,
                    "last": self._last_run,
                },
                "config": _public_config(config) if config is not None else None,
            }

    def read_state(self) -> dict[str, Any]:
        with self._lock:
            config = self._config
            if config is None:
                raise RuntimeError("Config not loaded")
            state_path = config.state_file
        return load_state(state_path)

    def get_storage_capabilities(self) -> dict[str, Any]:
        with self._lock:
            config = copy.deepcopy(self._config) if self._config is not None else None
        if config is None:
            raise RuntimeError("Config not loaded")
        mode = str(getattr(config, "storage_mode", "local") or "local")
        if mode != "webdav":
            return {"mode": mode, "ok": True, "capabilities": {}}
        try:
            client = WebDAVClient(config.webdav)
            capabilities = client.detect_capabilities()
            return {"mode": mode, "ok": True, "capabilities": capabilities}
        except Exception as exc:
            return {"mode": mode, "ok": False, "capabilities": {}, "error": str(exc)}

    def get_storage_health(self) -> dict[str, Any]:
        with self._lock:
            config = copy.deepcopy(self._config) if self._config is not None else None
        if config is None:
            raise RuntimeError("Config not loaded")
        state = load_state(config.state_file)
        repos_state = state.get("repos", {}) if isinstance(state.get("repos"), dict) else {}
        totals = {
            "upload_retry_total": 0,
            "upload_verify_failed_total": 0,
            "upload_queue_depth": 0,
        }
        repos: list[dict[str, Any]] = []
        for repo_key, repo_state in repos_state.items():
            if not isinstance(repo_key, str):
                continue
            if not isinstance(repo_state, dict):
                repo_state = {}
            stats = repo_state.get("stats", {}) if isinstance(repo_state.get("stats"), dict) else {}
            retry_total = int(stats.get("upload_retry_total", 0) or 0)
            verify_failed_total = int(stats.get("upload_verify_failed_total", 0) or 0)
            queue_depth = int(stats.get("upload_queue_depth", 0) or 0)
            totals["upload_retry_total"] += retry_total
            totals["upload_verify_failed_total"] += verify_failed_total
            totals["upload_queue_depth"] += queue_depth
            repos.append(
                {
                    "repo": repo_key,
                    "upload_retry_total": retry_total,
                    "upload_verify_failed_total": verify_failed_total,
                    "upload_queue_depth": queue_depth,
                }
            )
        return {"mode": str(getattr(config, "storage_mode", "local") or "local"), "totals": totals, "repos": repos}

    def sync_webdav_cache(self, *, prune: bool = False) -> dict[str, Any]:
        with self._lock:
            config = copy.deepcopy(self._config) if self._config is not None else None
        if config is None:
            raise RuntimeError("Config not loaded")
        mode = str(getattr(config, "storage_mode", "local") or "local")
        cache_root = config.download_dir / ".webdav_cache"
        if mode != "webdav":
            return {
                "mode": mode,
                "prune": bool(prune),
                "totals": {
                    "repos_processed": 0,
                    "cache_files_checked": 0,
                    "expected_files": 0,
                    "stale_files": 0,
                    "missing_files": 0,
                    "pruned_files": 0,
                },
                "items": [],
            }

        state = load_state(config.state_file)
        repos_state = state.get("repos", {}) if isinstance(state.get("repos"), dict) else {}

        totals = {
            "repos_processed": 0,
            "cache_files_checked": 0,
            "expected_files": 0,
            "stale_files": 0,
            "missing_files": 0,
            "pruned_files": 0,
        }
        items: list[dict[str, Any]] = []

        for repo_key, repo_state in repos_state.items():
            if not isinstance(repo_key, str) or "/" not in repo_key:
                continue
            if not isinstance(repo_state, dict):
                repo_state = {}
            owner, repo = repo_key.split("/", 1)
            cache_repo_dir = cache_root / owner / repo
            releases = repo_state.get("releases", {}) if isinstance(repo_state.get("releases"), dict) else {}
            expected: set[str] = set()
            for tag, entry in releases.items():
                if not isinstance(tag, str) or not tag:
                    continue
                entry_dict = entry if isinstance(entry, dict) else {}
                assets = entry_dict.get("downloaded_assets", [])
                tag_dir = _sanitize_path_component(tag)
                if isinstance(assets, list):
                    for asset in assets:
                        if not isinstance(asset, str) or not asset:
                            continue
                        expected.add(f"{tag_dir}/{asset}")

            existing: set[str] = set()
            if cache_repo_dir.exists():
                for p in cache_repo_dir.rglob("*"):
                    if p.is_file():
                        try:
                            existing.add(str(p.relative_to(cache_repo_dir)).replace("\\", "/"))
                        except Exception:
                            continue

            stale = sorted(existing - expected)
            missing = sorted(expected - existing)
            pruned = 0
            if prune:
                for rel in stale:
                    p = cache_repo_dir / rel
                    try:
                        p.unlink()
                        pruned += 1
                    except FileNotFoundError:
                        continue
                    except Exception:
                        continue

            totals["repos_processed"] += 1
            totals["cache_files_checked"] += len(existing)
            totals["expected_files"] += len(expected)
            totals["stale_files"] += len(stale)
            totals["missing_files"] += len(missing)
            totals["pruned_files"] += pruned
            items.append(
                {
                    "repo": repo_key,
                    "cache_files_checked": len(existing),
                    "expected_files": len(expected),
                    "stale_files": len(stale),
                    "missing_files": len(missing),
                    "pruned_files": pruned,
                    "stale_examples": stale[:10],
                    "missing_examples": missing[:10],
                }
            )

        return {"mode": mode, "prune": bool(prune), "totals": totals, "items": items}

    def preview_cleanup(self, repo: str | None = None) -> dict[str, Any]:
        with self._lock:
            config = copy.deepcopy(self._config) if self._config is not None else None
        if config is None:
            raise RuntimeError("Config not loaded")
        state = load_state(config.state_file)
        repos_state = state.get("repos", {}) if isinstance(state.get("repos"), dict) else {}

        cfg_by_key: dict[str, RepoConfig] = {}
        for repo_cfg in config.repos:
            try:
                cfg_by_key[_repo_key_from_spec(repo_cfg.name)] = repo_cfg
            except Exception:
                cfg_by_key[repo_cfg.name] = repo_cfg

        def _entry_sort_key(entry: dict[str, Any]) -> datetime:
            for field in ("published_at", "created_at", "processed_at"):
                raw = entry.get(field)
                if not isinstance(raw, str) or not raw.strip():
                    continue
                try:
                    dt = datetime.fromisoformat(raw)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    return dt
                except Exception:
                    continue
            return datetime.min.replace(tzinfo=timezone.utc)

        def _build_for_repo(repo_key: str) -> dict[str, Any]:
            repo_cfg = cfg_by_key.get(repo_key)
            if repo_cfg is None:
                raise ValueError("unknown repo")
            keep_last = int(repo_cfg.keep_last or config.keep_last)
            repo_state = repos_state.get(repo_key, {}) if isinstance(repos_state.get(repo_key), dict) else {}
            releases = repo_state.get("releases", {}) if isinstance(repo_state.get("releases"), dict) else {}
            rows: list[tuple[str, datetime]] = []
            for tag, entry in releases.items():
                if not isinstance(tag, str) or not tag:
                    continue
                if not isinstance(entry, dict):
                    entry = {}
                rows.append((tag, _entry_sort_key(entry)))
            rows.sort(key=lambda x: x[1], reverse=True)
            keep_tags = [tag for tag, _ in rows[:keep_last]]
            delete_tags = [tag for tag, _ in rows[keep_last:]]
            return {
                "repo": repo_key,
                "keep_last": keep_last,
                "keep_tags": keep_tags,
                "delete_tags": delete_tags,
                "delete_count": len(delete_tags),
            }

        if repo is not None:
            repo_key = _repo_key_from_spec(str(repo))
            return _build_for_repo(repo_key)

        items = []
        for repo_key in sorted(cfg_by_key.keys()):
            items.append(_build_for_repo(repo_key))
        return {"items": items}

    def list_repo_summaries(self) -> list[dict[str, Any]]:
        with self._lock:
            config = copy.deepcopy(self._config) if self._config is not None else None
            next_runs = dict(self._repo_next_run_at)
            scheduler_enabled = bool(self._scheduler_enabled)

        if config is None:
            raise RuntimeError("Config not loaded")

        state = load_state(config.state_file)
        repos_state = state.get("repos", {}) if isinstance(state.get("repos"), dict) else {}

        items: list[dict[str, Any]] = []
        for repo_cfg in config.repos:
            try:
                key = _repo_key_from_spec(repo_cfg.name)
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

    def get_repo_summary(self, repo_key: str) -> dict[str, Any]:
        repo_key = str(repo_key or "").strip()
        if not repo_key:
            raise ValueError("repo_key required")

        with self._lock:
            config = copy.deepcopy(self._config) if self._config is not None else None
            next_run_at = self._repo_next_run_at.get(repo_key) if self._scheduler_enabled else None

        if config is None:
            raise RuntimeError("Config not loaded")

        state = load_state(config.state_file)
        repos_state = state.get("repos", {}) if isinstance(state.get("repos"), dict) else {}
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
                key = _repo_key_from_spec(repo_cfg.name)
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

    def get_repo_activity(self, repo_key: str, *, limit: int = 200) -> list[dict[str, Any]]:
        repo_key = str(repo_key or "").strip()
        if not repo_key:
            raise ValueError("repo_key required")
        limit = max(1, min(int(limit), 2000))

        with self._lock:
            config = copy.deepcopy(self._config) if self._config is not None else None

        if config is None:
            raise RuntimeError("Config not loaded")

        state = load_state(config.state_file)
        repos_state = state.get("repos", {}) if isinstance(state.get("repos"), dict) else {}
        repo_state = repos_state.get(repo_key, {}) if isinstance(repos_state.get(repo_key), dict) else {}
        items = repo_state.get("activity", []) if isinstance(repo_state.get("activity"), list) else []
        tail = items[-limit:]
        return [x for x in tail if isinstance(x, dict)]

    def get_repo_releases(self, repo_key: str, *, limit: int = 100) -> list[dict[str, Any]]:
        repo_key = str(repo_key or "").strip()
        if not repo_key:
            raise ValueError("repo_key required")
        limit = max(1, min(int(limit), 2000))

        with self._lock:
            config = copy.deepcopy(self._config) if self._config is not None else None

        if config is None:
            raise RuntimeError("Config not loaded")

        known = False
        for repo_cfg in config.repos:
            try:
                key = _repo_key_from_spec(repo_cfg.name)
            except Exception:
                key = repo_cfg.name
            if key == repo_key:
                known = True
                break
        if not known:
            raise ValueError("unknown repo")

        state = load_state(config.state_file)
        repos_state = state.get("repos", {}) if isinstance(state.get("repos"), dict) else {}
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
                    "_sort_ts": parse_ts(entry.get("published_at")) or parse_ts(entry.get("created_at")) or parse_ts(entry.get("processed_at")) or datetime.min.replace(tzinfo=timezone.utc),
                }
            )

        items.sort(key=lambda x: x.get("_sort_ts") or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        for x in items:
            x.pop("_sort_ts", None)
        return items[:limit]

    def test_webdav(self, patch: dict[str, Any] | None = None) -> None:
        with self._lock:
            config = self._config
            if config is None:
                raise RuntimeError("Config not loaded")
            base = config.webdav

        base_url = str(getattr(base, "base_url", "") or "")
        username = getattr(base, "username", None)
        password = getattr(base, "password", None)
        verify_tls = bool(getattr(base, "verify_tls", True))
        timeout_seconds = int(getattr(base, "timeout_seconds", 60) or 60)

        if patch and isinstance(patch, dict):
            if "base_url" in patch:
                base_url = str(patch.get("base_url") or "").strip()
            if "username" in patch:
                raw_user = patch.get("username")
                username = str(raw_user).strip() if isinstance(raw_user, str) and raw_user.strip() else None
            if "password" in patch:
                raw_pass = patch.get("password")
                if isinstance(raw_pass, str) and raw_pass != "":
                    password = raw_pass
                if raw_pass is None:
                    password = None
            if "verify_tls" in patch:
                verify_tls = bool(patch.get("verify_tls", True))
            if "timeout_seconds" in patch:
                timeout_seconds = _safe_int(patch.get("timeout_seconds"), min_value=5, max_value=600)

        client = WebDAVClient(
            WebDAVConfig(
                base_url=base_url,
                username=username,
                password=password,
                verify_tls=verify_tls,
                timeout_seconds=timeout_seconds,
            )
        )
        client.test_connection()

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                task = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if task.get("type") == "run_once":
                raw_repo_keys = task.get("repo_keys")
                repo_keys = raw_repo_keys if isinstance(raw_repo_keys, list) else None
                self._do_run_once(task.get("repo_key"), repo_keys=repo_keys)

    def _do_run_once(self, repo_key: str | None, *, repo_keys: list[str] | None = None) -> None:
        with self._lock:
            self._run_requested = False
            if self._run_in_progress:
                return
            self._run_in_progress = True
            self._run_id += 1
            run_id = self._run_id
            config_snapshot = copy.deepcopy(self._config) if self._config is not None else None
            if self._last_run:
                self._last_run["id"] = run_id
                self._last_run["started_at"] = _utc_now_iso()

        exit_code: int | None = None
        error: str | None = None
        processed_keys: list[str] = []
        try:
            if config_snapshot is None:
                raise RuntimeError("Config not loaded")
            if repo_key is not None and repo_keys is not None:
                raise ValueError("invalid run request")
            if repo_keys is not None:
                requested = set(repo_keys)
                filtered: list[RepoConfig] = []
                seen: set[str] = set()
                for repo_cfg in config_snapshot.repos:
                    try:
                        key = _repo_key_from_spec(repo_cfg.name)
                    except Exception:
                        key = repo_cfg.name
                    if key in requested:
                        filtered.append(repo_cfg)
                        seen.add(key)
                if not filtered or seen != requested:
                    raise ValueError("unknown repo")
                config_snapshot.repos = filtered
                processed_keys = [k for k in repo_keys if k in seen]
            elif repo_key is not None:
                filtered: list[RepoConfig] = []
                for repo_cfg in config_snapshot.repos:
                    try:
                        key = _repo_key_from_spec(repo_cfg.name)
                    except Exception:
                        key = repo_cfg.name
                    if key == repo_key:
                        filtered.append(repo_cfg)
                if not filtered:
                    raise ValueError("unknown repo")
                config_snapshot.repos = filtered
                processed_keys = [repo_key]
            else:
                processed_keys = self._enabled_repo_keys(config_snapshot)
            exit_code = watcher_run_once(config_snapshot)
        except Exception as exc:
            error = str(exc)
            logging.exception("run_once failed")
        finally:
            now = time.time()
            if config_snapshot is not None and processed_keys and self._scheduler_enabled:
                try:
                    state = load_state(config_snapshot.state_file)
                except Exception:
                    state = {"repos": {}}
                repos_state = state.get("repos", {}) if isinstance(state.get("repos"), dict) else {}
                with self._lock:
                    for key in processed_keys:
                        repo_state = repos_state.get(key, {}) if isinstance(repos_state.get(key), dict) else {}
                        self._repo_next_run_at[key] = self._compute_next_repo_run_at(config_snapshot, repo_state, now=now)
                    self._sync_repo_schedule_locked()
                    self._refresh_global_next_run_at_locked()
            with self._lock:
                self._run_in_progress = False
                if self._last_run:
                    self._last_run["finished_at"] = _utc_now_iso()
                    self._last_run["exit_code"] = exit_code
                    self._last_run["error"] = error

    def _scheduler_loop(self) -> None:
        while not self._stop_event.is_set():
            now = time.time()
            due_repo: str | None = None
            next_run: float | None = None
            with self._lock:
                enabled = self._scheduler_enabled
                run_busy = self._run_requested or self._run_in_progress
                if enabled and self._repo_next_run_at:
                    next_run = min(self._repo_next_run_at.values())
                    if not run_busy:
                        for key, ts in self._repo_next_run_at.items():
                            if ts <= now and (due_repo is None or ts < self._repo_next_run_at.get(due_repo, ts)):
                                due_repo = key
                self._next_run_at = next_run if enabled else None

            if not enabled or next_run is None:
                self._stop_event.wait(timeout=0.5)
                continue

            if due_repo is not None:
                queued = self.enqueue_run_once(source="scheduler", repo=due_repo)
                if queued:
                    with self._lock:
                        # Temporary placeholder to avoid rapid re-queue attempts.
                        self._repo_next_run_at[due_repo] = now + 60
                        self._refresh_global_next_run_at_locked()
                continue

            self._stop_event.wait(timeout=min(0.5, max(0.0, next_run - now)))


class _Server(ThreadingHTTPServer):
    def __init__(
        self,
        server_address: tuple[str, int],
        handler_cls: type[BaseHTTPRequestHandler],
        *,
        app: WatcherService,
        ui: bool,
        auth: "AuthService",
    ):
        super().__init__(server_address, handler_cls)
        self.app = app
        self.ui = ui
        self.auth = auth


class Handler(BaseHTTPRequestHandler):
    server: _Server  # type: ignore[assignment]

    def log_message(self, fmt: str, *args: Any) -> None:
        logging.info("web %s - %s", self.address_string(), fmt % args)

    def do_GET(self) -> None:  # noqa: N802
        try:
            self._handle()
        except Exception:
            logging.exception("Unhandled error in GET handler")
            self._send_json({"error": "internal_error"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_POST(self) -> None:  # noqa: N802
        try:
            self._handle()
        except Exception:
            logging.exception("Unhandled error in POST handler")
            self._send_json({"error": "internal_error"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_PUT(self) -> None:  # noqa: N802
        try:
            self._handle()
        except Exception:
            logging.exception("Unhandled error in PUT handler")
            self._send_json({"error": "internal_error"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_OPTIONS(self) -> None:  # noqa: N802
        # CORS preflight: only echo same-origin requests.
        split = urlsplit(self.path)
        if split.path.startswith("/api/"):
            origin = self._allowed_cors_origin()
            if origin is None:
                self.send_response(HTTPStatus.FORBIDDEN)
                self.end_headers()
                return
            self.send_response(HTTPStatus.NO_CONTENT)
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "GET,POST,PUT,OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()
            return
        self.send_response(HTTPStatus.NO_CONTENT)
        self.end_headers()

    def _client_ip(self) -> str:
        xff = str(self.headers.get("X-Forwarded-For") or "").strip()
        if xff:
            return xff.split(",")[0].strip()
        return str(self.client_address[0] if self.client_address else "unknown")

    def _is_secure_request(self) -> bool:
        xfp = str(self.headers.get("X-Forwarded-Proto") or "").strip().lower()
        if xfp:
            return xfp == "https"
        forwarded = str(self.headers.get("Forwarded") or "").lower()
        if "proto=https" in forwarded:
            return True
        return bool(getattr(self.server, "server_port", None) == 443)

    def _allowed_cors_origin(self) -> str | None:
        origin = str(self.headers.get("Origin") or "").strip()
        if not origin:
            return None
        try:
            origin_split = urlsplit(origin)
            host = str(self.headers.get("Host") or "").strip().lower()
            if not origin_split.netloc or not host:
                return None
            if origin_split.netloc.lower() != host:
                return None
            return origin
        except Exception:
            return None

    def _set_cors_headers(self) -> None:
        origin = self._allowed_cors_origin()
        if origin is None:
            return
        self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Vary", "Origin")

    def _handle(self) -> None:
        split = urlsplit(self.path)
        path = split.path

        if path.startswith("/api/v1/"):
            self._handle_api(path, split)
            return

        if not self.server.ui:
            self._send_json({"error": "ui_disabled"}, status=HTTPStatus.NOT_FOUND)
            return

        if path == "/" or path == "":
            self._serve_static("index.html")
            return

        name = path.lstrip("/")
        if "/" in name or ".." in name or name.startswith("."):
            self._send_text("Not found", status=HTTPStatus.NOT_FOUND)
            return

        self._serve_static(name)

    def _handle_api(self, path: str, split) -> None:
        if path == "/api/v1/health" and self.command == "GET":
            self._send_json({"ok": True, "time": _utc_now_iso()})
            return

        if path == "/api/v1/login" and self.command == "POST":
            payload = self._read_json_body()
            if payload is None:
                return
            username = str(payload.get("username") or "")
            password = str(payload.get("password") or "")
            token, error_code = self.server.auth.login(username, password, self._client_ip())
            if token is None:
                if error_code == "rate_limited":
                    self._send_json({"error": "rate_limited"}, status=HTTPStatus.TOO_MANY_REQUESTS)
                    return
                self._send_json({"error": "invalid_credentials"}, status=HTTPStatus.UNAUTHORIZED)
                return

            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            cookie_flags = "Path=/; HttpOnly; SameSite=Lax"
            if self._is_secure_request():
                cookie_flags += "; Secure"
            self.send_header("Set-Cookie", f"grw_session={token}; {cookie_flags}")
            body = json.dumps(
                {
                    "ok": True,
                    "user": {
                        "username": self.server.app.auth_username(),
                        "must_change_password": self.server.app.must_change_password(),
                    },
                },
                ensure_ascii=False,
            ).encode("utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/api/v1/logout" and self.command == "POST":
            token = AuthService.get_token_from_cookie(self.headers.get("Cookie"))
            self.server.auth.delete_session(token)
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            cookie_flags = "Path=/; Max-Age=0; HttpOnly; SameSite=Lax"
            if self._is_secure_request():
                cookie_flags += "; Secure"
            self.send_header("Set-Cookie", f"grw_session=; {cookie_flags}")
            body = json.dumps({"ok": True}, ensure_ascii=False).encode("utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if not self._is_authenticated():
            self._send_json({"error": "unauthorized"}, status=HTTPStatus.UNAUTHORIZED)
            return

        if self.server.app.must_change_password() and self.command in ("POST", "PUT"):
            if path not in ("/api/v1/settings", "/api/v1/logout"):
                self._send_json({"error": "password_change_required"}, status=HTTPStatus.FORBIDDEN)
                return

        if path == "/api/v1/me" and self.command == "GET":
            self._send_json(
                {
                    "user": {
                        "username": self.server.app.auth_username(),
                        "must_change_password": self.server.app.must_change_password(),
                    }
                }
            )
            return

        if path == "/api/v1/status" and self.command == "GET":
            payload = self.server.app.snapshot()
            self._send_json(payload)
            return

        if path == "/api/v1/repos" and self.command == "GET":
            try:
                items = self.server.app.list_repo_summaries()
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            self._send_json({"items": items})
            return

        if path.startswith("/api/v1/repos/") and self.command == "GET":
            rest = path[len("/api/v1/repos/") :]
            parts = [p for p in rest.split("/") if p]
            if len(parts) >= 2:
                repo_key = f"{parts[0]}/{parts[1]}"
                if len(parts) == 2:
                    try:
                        data = self.server.app.get_repo_summary(repo_key)
                    except Exception as exc:
                        self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                        return
                    self._send_json({"repo": data})
                    return
                if len(parts) == 3 and parts[2] == "activity":
                    qs = parse_qs(split.query)
                    limit = 200
                    if "limit" in qs and qs["limit"]:
                        try:
                            limit = _safe_int(qs["limit"][0], min_value=1, max_value=2000)
                        except Exception:
                            limit = 200
                    try:
                        items = self.server.app.get_repo_activity(repo_key, limit=limit)
                    except Exception as exc:
                        self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                        return
                    self._send_json({"items": items})
                    return
                if len(parts) == 3 and parts[2] == "releases":
                    qs = parse_qs(split.query)
                    limit = 100
                    if "limit" in qs and qs["limit"]:
                        try:
                            limit = _safe_int(qs["limit"][0], min_value=1, max_value=2000)
                        except Exception:
                            limit = 100
                    try:
                        items = self.server.app.get_repo_releases(repo_key, limit=limit)
                    except Exception as exc:
                        self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                        return
                    self._send_json({"items": items})
                    return

        if path == "/api/v1/config" and self.command == "GET":
            payload = self.server.app.snapshot().get("config")
            self._send_json({"config": payload})
            return

        if path == "/api/v1/logs" and self.command == "GET":
            qs = parse_qs(split.query)
            limit = 200
            if "limit" in qs and qs["limit"]:
                try:
                    limit = _safe_int(qs["limit"][0], min_value=1, max_value=2000)
                except Exception:
                    limit = 200

            handler = _find_activity_handler()
            self._send_json({"items": handler.snapshot(limit) if handler else [], "log_file": self.server.app.snapshot().get("log_file")})
            return

        if path == "/api/v1/state" and self.command == "GET":
            try:
                state = self.server.app.read_state()
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            self._send_json({"state": state})
            return

        if path == "/api/v1/storage/capabilities" and self.command == "GET":
            try:
                payload = self.server.app.get_storage_capabilities()
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            self._send_json(payload)
            return

        if path == "/api/v1/storage/health" and self.command == "GET":
            try:
                payload = self.server.app.get_storage_health()
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            self._send_json(payload)
            return

        if path == "/api/v1/storage/sync-cache" and self.command == "POST":
            payload = self._read_json_body()
            if payload is None:
                return
            prune = bool(payload.get("prune", False))
            try:
                result = self.server.app.sync_webdav_cache(prune=prune)
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            self._send_json(result)
            return

        if path == "/api/v1/storage/test" and self.command == "POST":
            payload = self._read_json_body()
            if payload is None:
                return
            webdav_patch = payload.get("webdav") if isinstance(payload.get("webdav"), dict) else payload
            try:
                self.server.app.test_webdav(webdav_patch if isinstance(webdav_patch, dict) else None)
            except (WebDAVError, ValueError, RuntimeError) as exc:
                self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
                return
            self._send_json({"ok": True})
            return

        if path == "/api/v1/cleanup/preview" and self.command == "POST":
            payload = self._read_json_body()
            if payload is None:
                return
            repo = payload.get("repo")
            try:
                preview = self.server.app.preview_cleanup(repo=repo if isinstance(repo, str) and repo.strip() else None)
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            self._send_json(preview)
            return

        if path == "/api/v1/run" and self.command == "POST":
            payload = self._read_json_body()
            if payload is None:
                return
            repo = payload.get("repo")
            repos = payload.get("repos")
            if "repos" in payload and not isinstance(repos, list):
                self._send_json({"error": "repos must be a list"}, status=HTTPStatus.BAD_REQUEST)
                return
            try:
                queued = self.server.app.enqueue_run_once(
                    source="api",
                    repo=repo if repo is not None else None,
                    repos=repos if isinstance(repos, list) else None,
                )
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            self._send_json({"queued": queued, "status": self.server.app.snapshot()["run"]["last"]})
            return

        if path == "/api/v1/scheduler" and self.command == "PUT":
            payload = self._read_json_body()
            if payload is None:
                return
            enabled = bool(payload.get("enabled", True))
            self.server.app.set_scheduler(enabled)
            self._send_json({"ok": True, "scheduler": self.server.app.snapshot()["scheduler"]})
            return

        if path == "/api/v1/settings" and self.command == "PUT":
            payload = self._read_json_body()
            if payload is None:
                return
            try:
                self.server.app.update_settings(payload)
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            self._send_json({"ok": True, "config": self.server.app.snapshot()["config"]})
            return

        if path == "/api/v1/reload" and self.command == "POST":
            self.server.app.reload_config()
            self._send_json({"ok": True, "status": self.server.app.snapshot()})
            return

        self._send_json({"error": "not_found"}, status=HTTPStatus.NOT_FOUND)

    def _is_authenticated(self) -> bool:
        token = AuthService.get_token_from_cookie(self.headers.get("Cookie"))
        return self.server.auth.is_valid(token)

    def _read_json_body(self) -> dict[str, Any] | None:
        length = self.headers.get("Content-Length")
        if not length:
            return {}
        try:
            n = int(length)
        except ValueError:
            self._send_json({"error": "invalid_content_length"}, status=HTTPStatus.BAD_REQUEST)
            return None
        if n < 0 or n > 256 * 1024:
            self._send_json({"error": "payload_too_large"}, status=HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            return None
        raw = self.rfile.read(n)
        if not raw:
            return {}
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            self._send_json({"error": "invalid_json"}, status=HTTPStatus.BAD_REQUEST)
            return None
        if not isinstance(payload, dict):
            self._send_json({"error": "json_must_be_object"}, status=HTTPStatus.BAD_REQUEST)
            return None
        return payload

    def _send_json(self, data: Any, *, status: HTTPStatus = HTTPStatus.OK) -> None:
        encoded = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        if self.path.startswith("/api/"):
            self._set_cors_headers()
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_text(self, text: str, *, status: HTTPStatus = HTTPStatus.OK, content_type: str = "text/plain; charset=utf-8") -> None:
        encoded = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _serve_static(self, filename: str) -> None:
        static_root = resources.files("github_release_watcher").joinpath("static")
        candidate = static_root.joinpath(filename)
        try:
            data = candidate.read_bytes()
        except FileNotFoundError:
            self._send_text("Not found", status=HTTPStatus.NOT_FOUND)
            return

        content_type = "application/octet-stream"
        if filename.endswith(".html"):
            content_type = "text/html; charset=utf-8"
        elif filename.endswith(".css"):
            content_type = "text/css; charset=utf-8"
        elif filename.endswith(".js"):
            content_type = "application/javascript; charset=utf-8"
        elif filename.endswith(".svg"):
            content_type = "image/svg+xml"

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def _find_activity_handler() -> ActivityBuffer | None:
    root = logging.getLogger()
    for h in root.handlers:
        if isinstance(h, ActivityBuffer):
            return h
    return None


def serve(
    *,
    config_path: Path,
    log_file: Path | None = None,
    host: str = "127.0.0.1",
    port: int = 8000,
    ui: bool = True,
    scheduler_enabled: bool = True,
    run_immediately: bool = True,
) -> int:
    root_logger = logging.getLogger()
    if not any(isinstance(h, ActivityBuffer) for h in root_logger.handlers):
        root_logger.addHandler(ActivityBuffer(capacity=600))

    app = WatcherService(config_path, log_file=log_file)
    app.start(scheduler_enabled=scheduler_enabled, run_immediately=run_immediately)

    auth = AuthService(app)
    server = _Server((host, int(port)), Handler, app=app, ui=ui, auth=auth)
    logging.info("Web server listening on http://%s:%s (ui=%s)", host, port, ui)
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        logging.info("Shutting down web server...")
    finally:
        try:
            server.shutdown()
        except Exception:
            pass
        try:
            server.server_close()
        except Exception:
            pass
        app.shutdown()
    return 0
