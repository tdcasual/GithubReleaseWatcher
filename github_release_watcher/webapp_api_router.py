from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from http import HTTPStatus
from typing import Any
from urllib.parse import parse_qs

from .auth_service import AuthService
from .webapp_payloads import _safe_int
from .webdav import WebDAVError


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _find_activity_handler() -> Any:
    root = logging.getLogger()
    for handler in root.handlers:
        if handler.__class__.__name__ != "ActivityBuffer":
            continue
        snapshot = getattr(handler, "snapshot", None)
        if callable(snapshot):
            return handler
    return None


def handle_api_request(request_handler, path: str, split) -> None:
    if path == "/api/v1/health" and request_handler.command == "GET":
        request_handler._send_json({"ok": True, "time": _utc_now_iso()})
        return

    if path == "/api/v1/login" and request_handler.command == "POST":
        payload = request_handler._read_json_body()
        if payload is None:
            return
        username = str(payload.get("username") or "")
        password = str(payload.get("password") or "")
        token, error_code = request_handler.server.auth.login(username, password, request_handler._client_ip())
        if token is None:
            if error_code == "rate_limited":
                request_handler._send_json({"error": "rate_limited"}, status=HTTPStatus.TOO_MANY_REQUESTS)
                return
            request_handler._send_json({"error": "invalid_credentials"}, status=HTTPStatus.UNAUTHORIZED)
            return

        request_handler.send_response(HTTPStatus.OK)
        request_handler.send_header("Content-Type", "application/json; charset=utf-8")
        cookie_flags = "Path=/; HttpOnly; SameSite=Lax"
        if request_handler._is_secure_request():
            cookie_flags += "; Secure"
        request_handler.send_header("Set-Cookie", f"grw_session={token}; {cookie_flags}")
        body = json.dumps(
            {
                "ok": True,
                "user": {
                    "username": request_handler.server.app.auth_username(),
                    "must_change_password": request_handler.server.app.must_change_password(),
                },
            },
            ensure_ascii=False,
        ).encode("utf-8")
        request_handler.send_header("Content-Length", str(len(body)))
        request_handler.end_headers()
        request_handler.wfile.write(body)
        return

    if path == "/api/v1/logout" and request_handler.command == "POST":
        token = AuthService.get_token_from_cookie(request_handler.headers.get("Cookie"))
        request_handler.server.auth.delete_session(token)
        request_handler.send_response(HTTPStatus.OK)
        request_handler.send_header("Content-Type", "application/json; charset=utf-8")
        cookie_flags = "Path=/; Max-Age=0; HttpOnly; SameSite=Lax"
        if request_handler._is_secure_request():
            cookie_flags += "; Secure"
        request_handler.send_header("Set-Cookie", f"grw_session=; {cookie_flags}")
        body = json.dumps({"ok": True}, ensure_ascii=False).encode("utf-8")
        request_handler.send_header("Content-Length", str(len(body)))
        request_handler.end_headers()
        request_handler.wfile.write(body)
        return

    if not request_handler._is_authenticated():
        request_handler._send_json({"error": "unauthorized"}, status=HTTPStatus.UNAUTHORIZED)
        return

    if request_handler.server.app.must_change_password() and request_handler.command in ("POST", "PUT"):
        if path not in ("/api/v1/settings", "/api/v1/logout"):
            request_handler._send_json({"error": "password_change_required"}, status=HTTPStatus.FORBIDDEN)
            return

    if path == "/api/v1/me" and request_handler.command == "GET":
        request_handler._send_json(
            {
                "user": {
                    "username": request_handler.server.app.auth_username(),
                    "must_change_password": request_handler.server.app.must_change_password(),
                }
            }
        )
        return

    if path == "/api/v1/status" and request_handler.command == "GET":
        payload = request_handler.server.app.snapshot()
        request_handler._send_json(payload)
        return

    if path == "/api/v1/repos" and request_handler.command == "GET":
        try:
            items = request_handler.server.app.list_repo_summaries()
        except Exception as exc:
            request_handler._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return
        request_handler._send_json({"items": items})
        return

    if path.startswith("/api/v1/repos/") and request_handler.command == "GET":
        rest = path[len("/api/v1/repos/") :]
        parts = [p for p in rest.split("/") if p]
        if len(parts) >= 2:
            repo_key = f"{parts[0]}/{parts[1]}"
            if len(parts) == 2:
                try:
                    data = request_handler.server.app.get_repo_summary(repo_key)
                except Exception as exc:
                    request_handler._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                    return
                request_handler._send_json({"repo": data})
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
                    items = request_handler.server.app.get_repo_activity(repo_key, limit=limit)
                except Exception as exc:
                    request_handler._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                    return
                request_handler._send_json({"items": items})
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
                    items = request_handler.server.app.get_repo_releases(repo_key, limit=limit)
                except Exception as exc:
                    request_handler._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                    return
                request_handler._send_json({"items": items})
                return

    if path == "/api/v1/config" and request_handler.command == "GET":
        payload = request_handler.server.app.snapshot().get("config")
        request_handler._send_json({"config": payload})
        return

    if path == "/api/v1/logs" and request_handler.command == "GET":
        qs = parse_qs(split.query)
        limit = 200
        if "limit" in qs and qs["limit"]:
            try:
                limit = _safe_int(qs["limit"][0], min_value=1, max_value=2000)
            except Exception:
                limit = 200

        activity_handler = _find_activity_handler()
        request_handler._send_json(
            {
                "items": activity_handler.snapshot(limit) if activity_handler else [],
                "log_file": request_handler.server.app.snapshot().get("log_file"),
            }
        )
        return

    if path == "/api/v1/state" and request_handler.command == "GET":
        try:
            state = request_handler.server.app.read_state()
        except Exception as exc:
            request_handler._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return
        request_handler._send_json({"state": state})
        return

    if path == "/api/v1/storage/capabilities" and request_handler.command == "GET":
        try:
            payload = request_handler.server.app.get_storage_capabilities()
        except Exception as exc:
            request_handler._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return
        request_handler._send_json(payload)
        return

    if path == "/api/v1/storage/health" and request_handler.command == "GET":
        try:
            payload = request_handler.server.app.get_storage_health()
        except Exception as exc:
            request_handler._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return
        request_handler._send_json(payload)
        return

    if path == "/api/v1/storage/sync-cache" and request_handler.command == "POST":
        payload = request_handler._read_json_body()
        if payload is None:
            return
        prune = bool(payload.get("prune", False))
        try:
            result = request_handler.server.app.sync_webdav_cache(prune=prune)
        except Exception as exc:
            request_handler._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return
        request_handler._send_json(result)
        return

    if path == "/api/v1/storage/test" and request_handler.command == "POST":
        payload = request_handler._read_json_body()
        if payload is None:
            return
        webdav_patch = payload.get("webdav") if isinstance(payload.get("webdav"), dict) else payload
        try:
            request_handler.server.app.test_webdav(webdav_patch if isinstance(webdav_patch, dict) else None)
        except (WebDAVError, ValueError, RuntimeError) as exc:
            request_handler._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return
        except Exception as exc:
            request_handler._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        request_handler._send_json({"ok": True})
        return

    if path == "/api/v1/cleanup/preview" and request_handler.command == "POST":
        payload = request_handler._read_json_body()
        if payload is None:
            return
        repo = payload.get("repo")
        try:
            preview = request_handler.server.app.preview_cleanup(repo=repo if isinstance(repo, str) and repo.strip() else None)
        except Exception as exc:
            request_handler._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return
        request_handler._send_json(preview)
        return

    if path == "/api/v1/run" and request_handler.command == "POST":
        payload = request_handler._read_json_body()
        if payload is None:
            return
        repo = payload.get("repo")
        repos = payload.get("repos")
        if "repos" in payload and not isinstance(repos, list):
            request_handler._send_json({"error": "repos must be a list"}, status=HTTPStatus.BAD_REQUEST)
            return
        try:
            queued = request_handler.server.app.enqueue_run_once(
                source="api",
                repo=repo if repo is not None else None,
                repos=repos if isinstance(repos, list) else None,
            )
        except Exception as exc:
            request_handler._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return
        request_handler._send_json({"queued": queued, "status": request_handler.server.app.snapshot()["run"]["last"]})
        return

    if path == "/api/v1/scheduler" and request_handler.command == "PUT":
        payload = request_handler._read_json_body()
        if payload is None:
            return
        enabled = bool(payload.get("enabled", True))
        request_handler.server.app.set_scheduler(enabled)
        request_handler._send_json({"ok": True, "scheduler": request_handler.server.app.snapshot()["scheduler"]})
        return

    if path == "/api/v1/settings" and request_handler.command == "PUT":
        payload = request_handler._read_json_body()
        if payload is None:
            return
        try:
            request_handler.server.app.update_settings(payload)
        except Exception as exc:
            request_handler._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return
        request_handler._send_json({"ok": True, "config": request_handler.server.app.snapshot()["config"]})
        return

    if path == "/api/v1/reload" and request_handler.command == "POST":
        request_handler.server.app.reload_config()
        request_handler._send_json({"ok": True, "status": request_handler.server.app.snapshot()})
        return

    request_handler._send_json({"error": "not_found"}, status=HTTPStatus.NOT_FOUND)
