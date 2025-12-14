from __future__ import annotations

import copy
import hashlib
import hmac
import json
import logging
import queue
import random
import re
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

from .config import AppConfig, ConfigError, RepoConfig, WebDAVConfig, load_config
from .github import parse_repo_spec
from .state import load_state
from .watcher import run_once as watcher_run_once
from .webdav import WebDAVClient, WebDAVError


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _safe_int(value: Any, *, min_value: int | None = None, max_value: int | None = None) -> int:
    if isinstance(value, bool):
        raise ValueError("not an int")
    if isinstance(value, int):
        num = value
    elif isinstance(value, str) and value.strip():
        num = int(value.strip())
    else:
        raise ValueError("not an int")
    if min_value is not None and num < min_value:
        raise ValueError(f"must be >= {min_value}")
    if max_value is not None and num > max_value:
        raise ValueError(f"must be <= {max_value}")
    return num


def _normalize_asset_type(raw: str) -> str:
    value = raw.strip().lower()
    if value.startswith("."):
        value = value[1:]
    if not value:
        raise ValueError("asset type is empty")
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,31}", value):
        raise ValueError("asset type has invalid characters")
    return value


def _normalize_asset_types(values: Any) -> list[str]:
    if values is None:
        return []
    if not isinstance(values, list):
        raise ValueError("asset_types must be a list")
    normalized: list[str] = []
    for item in values:
        if not isinstance(item, str):
            raise ValueError("asset_types must be a list of strings")
        norm = _normalize_asset_type(item)
        if norm not in normalized:
            normalized.append(norm)
    return normalized


def _compile_regex_list(values: Any, field_name: str) -> list[str]:
    if values is None:
        return []
    if not isinstance(values, list) or not all(isinstance(x, str) for x in values):
        raise ValueError(f"{field_name} must be a list of strings")
    for pattern in values:
        re.compile(pattern)
    return list(values)


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


def _pbkdf2_hash(password: str, *, salt_hex: str, iterations: int) -> str:
    salt = bytes.fromhex(salt_hex)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
    return dk.hex()


def _default_auth_config() -> dict[str, Any]:
    # Default credentials: admin/admin
    salt_hex = secrets.token_bytes(16).hex()
    iterations = 200_000
    return {
        "username": "admin",
        "salt": salt_hex,
        "iterations": iterations,
        "password_hash": _pbkdf2_hash("admin", salt_hex=salt_hex, iterations=iterations),
    }


def _load_auth_config(overrides: dict[str, Any]) -> dict[str, Any]:
    auth = overrides.get("auth", {}) if isinstance(overrides.get("auth"), dict) else {}
    username = auth.get("username")
    salt = auth.get("salt")
    iterations = auth.get("iterations")
    password_hash = auth.get("password_hash")

    if not isinstance(username, str) or not username.strip():
        return _default_auth_config()
    if not isinstance(salt, str) or not re.fullmatch(r"[0-9a-f]{16,128}", salt):
        return _default_auth_config()
    if not isinstance(iterations, int) or iterations < 50_000 or iterations > 2_000_000:
        return _default_auth_config()
    if not isinstance(password_hash, str) or not re.fullmatch(r"[0-9a-f]{32,128}", password_hash):
        return _default_auth_config()

    return {"username": username.strip(), "salt": salt, "iterations": int(iterations), "password_hash": password_hash}


def _verify_password(password: str, auth_config: dict[str, Any]) -> bool:
    try:
        expected = str(auth_config["password_hash"])
        got = _pbkdf2_hash(password, salt_hex=str(auth_config["salt"]), iterations=int(auth_config["iterations"]))
        return hmac.compare_digest(expected, got)
    except Exception:
        return False


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


def _repo_key_from_spec(spec: str) -> str:
    owner, repo, _ = parse_repo_spec(spec)
    return f"{owner}/{repo}"


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
            },
        },
        "repos": repos,
    }


def _resolve_path(base_dir: Path, raw: Any) -> Path:
    if not isinstance(raw, (str, Path)) or not str(raw).strip():
        raise ValueError("path must be a non-empty string")
    p = Path(str(raw).strip())
    return p if p.is_absolute() else (base_dir / p)


def _normalize_storage_mode(raw: Any) -> str:
    mode = str(raw or "").strip().lower()
    if mode in ("local", ""):
        return "local"
    if mode == "webdav":
        return "webdav"
    raise ValueError("storage.mode must be 'local' or 'webdav'")


def _apply_overrides(config: AppConfig, overrides: dict[str, Any], *, base_dir: Path) -> None:
    app_overrides = overrides.get("app", {}) if isinstance(overrides.get("app"), dict) else {}
    if "keep_last" in app_overrides:
        config.keep_last = _safe_int(app_overrides["keep_last"], min_value=1, max_value=1000)
    if "interval_seconds" in app_overrides:
        config.interval_seconds = _safe_int(app_overrides["interval_seconds"], min_value=1, max_value=31_536_000)

    storage_overrides = overrides.get("storage", {}) if isinstance(overrides.get("storage"), dict) else {}
    if storage_overrides:
        if "local_dir" in storage_overrides:
            config.download_dir = _resolve_path(base_dir, storage_overrides.get("local_dir"))

        if "mode" in storage_overrides:
            config.storage_mode = _normalize_storage_mode(storage_overrides.get("mode"))

        webdav_overrides = storage_overrides.get("webdav", {}) if isinstance(storage_overrides.get("webdav"), dict) else {}
        if webdav_overrides:
            if not hasattr(config, "webdav") or not isinstance(getattr(config, "webdav"), WebDAVConfig):
                config.webdav = WebDAVConfig()
            if "base_url" in webdav_overrides:
                config.webdav.base_url = str(webdav_overrides.get("base_url") or "").strip()
            if "username" in webdav_overrides:
                raw_user = webdav_overrides.get("username")
                config.webdav.username = str(raw_user).strip() if isinstance(raw_user, str) and raw_user.strip() else None
            if "password" in webdav_overrides:
                raw_pass = webdav_overrides.get("password")
                config.webdav.password = str(raw_pass) if isinstance(raw_pass, str) and raw_pass else None
            if "verify_tls" in webdav_overrides:
                config.webdav.verify_tls = bool(webdav_overrides.get("verify_tls", True))
            if "timeout_seconds" in webdav_overrides:
                config.webdav.timeout_seconds = _safe_int(webdav_overrides.get("timeout_seconds"), min_value=5, max_value=600)

        if str(getattr(config, "storage_mode", "local") or "local") == "webdav":
            if not str(getattr(getattr(config, "webdav", None), "base_url", "") or "").strip():
                raise ValueError("webdav.base_url is required when storage.mode = 'webdav'")

    repo_overrides = overrides.get("repos", {}) if isinstance(overrides.get("repos"), dict) else {}

    by_key: dict[str, RepoConfig] = {}
    for repo_cfg in config.repos:
        try:
            by_key[_repo_key_from_spec(repo_cfg.name)] = repo_cfg
        except Exception:
            by_key[repo_cfg.name] = repo_cfg

    for key, patch in repo_overrides.items():
        if not isinstance(key, str) or not isinstance(patch, dict):
            continue

        repo_cfg = by_key.get(key)
        if repo_cfg is None:
            name = str(patch.get("name") or key)
            repo_cfg = RepoConfig(name=name)
            config.repos.append(repo_cfg)
            by_key[key] = repo_cfg

        if "enabled" in patch:
            repo_cfg.enabled = bool(patch["enabled"])
        if "keep_last" in patch:
            raw_keep_last = patch["keep_last"]
            repo_cfg.keep_last = None if raw_keep_last is None else _safe_int(raw_keep_last, min_value=1, max_value=1000)
        if "asset_types" in patch:
            repo_cfg.asset_types = _normalize_asset_types(patch["asset_types"])
        if "include_assets" in patch:
            repo_cfg.include_assets = _compile_regex_list(patch["include_assets"], "include_assets")
        if "exclude_assets" in patch:
            repo_cfg.exclude_assets = _compile_regex_list(patch["exclude_assets"], "exclude_assets")
        if "include_prereleases" in patch:
            repo_cfg.include_prereleases = bool(patch["include_prereleases"])
        if "include_drafts" in patch:
            repo_cfg.include_drafts = bool(patch["include_drafts"])


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
        }
        overrides["updated_at"] = _utc_now_iso()
        _write_json_atomic(self._overrides_path, overrides)
        self.reload_config()

    def enqueue_run_once(self, *, source: str = "manual", repo: str | None = None) -> bool:
        repo_key: str | None = None
        if repo is not None:
            if not isinstance(repo, str) or not repo.strip():
                raise ValueError("repo must be a non-empty string")
            repo_key = _repo_key_from_spec(repo)

        with self._lock:
            if repo_key is not None:
                config = self._config
                if config is None:
                    raise RuntimeError("Config not loaded")
                existing = set()
                for repo_cfg in config.repos:
                    try:
                        existing.add(_repo_key_from_spec(repo_cfg.name))
                    except Exception:
                        existing.add(repo_cfg.name)
                if repo_key not in existing:
                    raise ValueError("unknown repo")

            if self._run_requested or self._run_in_progress:
                return False
            self._run_requested = True
            self._queue.put({"type": "run_once", "repo_key": repo_key})
            self._last_run = {
                "id": self._run_id + 1,
                "source": source,
                "repo": repo_key,
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
                self._do_run_once(task.get("repo_key"))

    def _do_run_once(self, repo_key: str | None) -> None:
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
            if repo_key is not None:
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


class AuthService:
    def __init__(self, app: WatcherService, *, session_ttl_seconds: int = 12 * 60 * 60):
        self._app = app
        self._ttl = max(60, int(session_ttl_seconds))
        self._lock = threading.Lock()
        self._sessions: dict[str, float] = {}

    def create_session(self, username: str) -> str:
        token = secrets.token_urlsafe(32)
        expires_at = time.time() + self._ttl
        with self._lock:
            self._sessions[token] = expires_at
        return token

    def delete_session(self, token: str | None) -> None:
        if not token:
            return
        with self._lock:
            self._sessions.pop(token, None)

    def is_valid(self, token: str | None) -> bool:
        if not token:
            return False
        now = time.time()
        with self._lock:
            expires_at = self._sessions.get(token)
            if expires_at is None:
                return False
            if now >= expires_at:
                self._sessions.pop(token, None)
                return False
        return True

    def login(self, username: str, password: str) -> str | None:
        if not self._app.verify_login(username, password):
            return None
        return self.create_session(username)

    @staticmethod
    def get_token_from_cookie(cookie_header: str | None) -> str | None:
        if not cookie_header:
            return None
        parts = [p.strip() for p in cookie_header.split(";") if p.strip()]
        for part in parts:
            if part.startswith("grw_session="):
                return part.split("=", 1)[1].strip() or None
        return None


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
        # Minimal CORS preflight support (useful when calling API from other origins).
        split = urlsplit(self.path)
        if split.path.startswith("/api/"):
            self.send_response(HTTPStatus.NO_CONTENT)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET,POST,PUT,OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()
            return
        self.send_response(HTTPStatus.NO_CONTENT)
        self.end_headers()

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
            token = self.server.auth.login(username, password)
            if token is None:
                self._send_json({"error": "invalid_credentials"}, status=HTTPStatus.UNAUTHORIZED)
                return

            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Set-Cookie", f"grw_session={token}; Path=/; HttpOnly; SameSite=Lax")
            body = json.dumps({"ok": True, "user": {"username": self.server.app.auth_username()}}, ensure_ascii=False).encode("utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/api/v1/logout" and self.command == "POST":
            token = AuthService.get_token_from_cookie(self.headers.get("Cookie"))
            self.server.auth.delete_session(token)
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Set-Cookie", "grw_session=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax")
            body = json.dumps({"ok": True}, ensure_ascii=False).encode("utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if not self._is_authenticated():
            self._send_json({"error": "unauthorized"}, status=HTTPStatus.UNAUTHORIZED)
            return

        if path == "/api/v1/me" and self.command == "GET":
            self._send_json({"user": {"username": self.server.app.auth_username()}})
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

        if path == "/api/v1/run" and self.command == "POST":
            payload = self._read_json_body()
            if payload is None:
                return
            repo = payload.get("repo")
            try:
                queued = self.server.app.enqueue_run_once(source="api", repo=repo if repo is not None else None)
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
            self.send_header("Access-Control-Allow-Origin", "*")
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
