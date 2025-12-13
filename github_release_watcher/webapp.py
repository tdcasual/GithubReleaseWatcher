from __future__ import annotations

import copy
import json
import logging
import queue
import re
import threading
import time
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from .config import AppConfig, ConfigError, RepoConfig, load_config
from .github import parse_repo_spec
from .state import load_state
from .watcher import run_once as watcher_run_once


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
        return {"version": 1, "updated_at": _utc_now_iso(), "app": {}, "repos": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "updated_at": _utc_now_iso(), "app": {}, "repos": {}}
    if not isinstance(data, dict):
        return {"version": 1, "updated_at": _utc_now_iso(), "app": {}, "repos": {}}
    if data.get("version") != 1:
        return {"version": 1, "updated_at": _utc_now_iso(), "app": {}, "repos": {}}
    data.setdefault("app", {})
    data.setdefault("repos", {})
    if not isinstance(data["app"], dict):
        data["app"] = {}
    if not isinstance(data["repos"], dict):
        data["repos"] = {}
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
            "fetch_path": config.fetch_path,
        },
        "github": {
            "api_base": config.github.api_base,
            "token_configured": bool(config.github.token),
        },
        "repos": repos,
    }


def _apply_overrides(config: AppConfig, overrides: dict[str, Any]) -> None:
    app_overrides = overrides.get("app", {}) if isinstance(overrides.get("app"), dict) else {}
    if "keep_last" in app_overrides:
        config.keep_last = _safe_int(app_overrides["keep_last"], min_value=1, max_value=1000)
    if "interval_seconds" in app_overrides:
        config.interval_seconds = _safe_int(app_overrides["interval_seconds"], min_value=1, max_value=86_400)

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


class RingLogBuffer(logging.Handler):
    def __init__(self, capacity: int = 500):
        super().__init__(level=logging.NOTSET)
        self._lock = threading.Lock()
        self._capacity = max(50, int(capacity))
        self._items: list[dict[str, Any]] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            payload = {
                "time": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
            }
            if record.exc_info:
                payload["exception"] = self.formatException(record.exc_info)
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
    def __init__(self, config_path: Path, overrides_path: Path | None = None):
        self._config_path = config_path
        self._overrides_path = overrides_path or config_path.with_name("config.override.json")

        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._queue: queue.Queue[str] = queue.Queue()

        self._scheduler_enabled = True
        self._next_run_at: float | None = None

        self._run_requested = False
        self._run_in_progress = False
        self._run_id = 0

        self._started_at = _utc_now_iso()
        self._last_config_reload_at: str | None = None
        self._config_error: str | None = None
        self._config: AppConfig | None = None
        self._overrides: dict[str, Any] = {}

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
                self._next_run_at = time.time() if run_immediately else time.time() + self._interval_seconds(default=60)
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

    def reload_config(self) -> None:
        with self._lock:
            self._config_error = None
            self._last_config_reload_at = _utc_now_iso()
            self._overrides = _read_json_file(self._overrides_path)

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
                _apply_overrides(config, self._overrides)
            except Exception as exc:
                self._config_error = f"Invalid overrides: {exc}"
                logging.exception("Failed applying overrides; continuing with base config")

            self._config = config

    def enqueue_run_once(self, *, source: str = "manual") -> bool:
        with self._lock:
            if self._run_requested or self._run_in_progress:
                return False
            self._run_requested = True
            self._queue.put("run_once")
            self._last_run = {
                "id": self._run_id + 1,
                "source": source,
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
            if self._scheduler_enabled and self._next_run_at is None:
                self._next_run_at = time.time()
            if not self._scheduler_enabled:
                self._next_run_at = None

    def update_settings(self, payload: dict[str, Any]) -> None:
        overrides = _read_json_file(self._overrides_path)

        app_patch = payload.get("app", {}) if isinstance(payload.get("app"), dict) else {}
        if "keep_last" in app_patch:
            overrides.setdefault("app", {})["keep_last"] = _safe_int(app_patch["keep_last"], min_value=1, max_value=1000)
        if "interval_seconds" in app_patch:
            overrides.setdefault("app", {})["interval_seconds"] = _safe_int(
                app_patch["interval_seconds"], min_value=1, max_value=86_400
            )

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
            next_run_at = self._next_run_at
            config = self._config
            return {
                "started_at": self._started_at,
                "config_path": str(self._config_path),
                "overrides_path": str(self._overrides_path),
                "config_loaded": config is not None,
                "config_error": self._config_error,
                "last_config_reload_at": self._last_config_reload_at,
                "scheduler": {
                    "enabled": self._scheduler_enabled,
                    "next_run_at": datetime.fromtimestamp(next_run_at, tz=timezone.utc).isoformat() if next_run_at else None,
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

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                task = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if task == "run_once":
                self._do_run_once()

    def _do_run_once(self) -> None:
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
        try:
            if config_snapshot is None:
                raise RuntimeError("Config not loaded")
            exit_code = watcher_run_once(config_snapshot)
        except Exception as exc:
            error = str(exc)
            logging.exception("run_once failed")
        finally:
            with self._lock:
                self._run_in_progress = False
                if self._last_run:
                    self._last_run["finished_at"] = _utc_now_iso()
                    self._last_run["exit_code"] = exit_code
                    self._last_run["error"] = error

    def _scheduler_loop(self) -> None:
        while not self._stop_event.is_set():
            with self._lock:
                enabled = self._scheduler_enabled
                next_run = self._next_run_at

            if not enabled or next_run is None:
                self._stop_event.wait(timeout=0.5)
                continue

            now = time.time()
            if now >= next_run:
                self.enqueue_run_once(source="scheduler")
                interval = self._interval_seconds(default=60)
                with self._lock:
                    self._next_run_at = now + interval
                continue

            self._stop_event.wait(timeout=min(0.5, max(0.0, next_run - now)))


class _Server(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], handler_cls: type[BaseHTTPRequestHandler], *, app: WatcherService, ui: bool):
        super().__init__(server_address, handler_cls)
        self.app = app
        self.ui = ui


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

        if path == "/api/v1/status" and self.command == "GET":
            payload = self.server.app.snapshot()
            self._send_json(payload)
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

            handler = _find_ring_log_handler()
            self._send_json({"items": handler.snapshot(limit) if handler else []})
            return

        if path == "/api/v1/state" and self.command == "GET":
            try:
                state = self.server.app.read_state()
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            self._send_json({"state": state})
            return

        if path == "/api/v1/run" and self.command == "POST":
            queued = self.server.app.enqueue_run_once(source="api")
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


def _find_ring_log_handler() -> RingLogBuffer | None:
    root = logging.getLogger()
    for h in root.handlers:
        if isinstance(h, RingLogBuffer):
            return h
    return None


def serve(
    *,
    config_path: Path,
    host: str = "127.0.0.1",
    port: int = 8000,
    ui: bool = True,
    scheduler_enabled: bool = True,
    run_immediately: bool = True,
) -> int:
    root_logger = logging.getLogger()
    if not any(isinstance(h, RingLogBuffer) for h in root_logger.handlers):
        root_logger.addHandler(RingLogBuffer(capacity=800))

    app = WatcherService(config_path)
    app.start(scheduler_enabled=scheduler_enabled, run_immediately=run_immediately)

    server = _Server((host, int(port)), Handler, app=app, ui=ui)
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
