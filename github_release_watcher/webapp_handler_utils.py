from __future__ import annotations

import json
from http import HTTPStatus
from importlib import resources
from typing import Any
from urllib.parse import urlsplit


def allowed_cors_origin(request_handler) -> str | None:
    origin = str(request_handler.headers.get("Origin") or "").strip()
    if not origin:
        return None
    try:
        origin_split = urlsplit(origin)
        host = str(request_handler.headers.get("Host") or "").strip().lower()
        if not origin_split.netloc or not host:
            return None
        if origin_split.netloc.lower() != host:
            return None
        return origin
    except Exception:
        return None


def handle_options_preflight(request_handler) -> None:
    # CORS preflight: only echo same-origin requests.
    split = urlsplit(request_handler.path)
    if split.path.startswith("/api/"):
        origin = allowed_cors_origin(request_handler)
        if origin is None:
            request_handler.send_response(HTTPStatus.FORBIDDEN)
            request_handler.end_headers()
            return
        request_handler.send_response(HTTPStatus.NO_CONTENT)
        request_handler.send_header("Access-Control-Allow-Origin", origin)
        request_handler.send_header("Vary", "Origin")
        request_handler.send_header("Access-Control-Allow-Methods", "GET,POST,PUT,OPTIONS")
        request_handler.send_header("Access-Control-Allow-Headers", "Content-Type")
        request_handler.end_headers()
        return
    request_handler.send_response(HTTPStatus.NO_CONTENT)
    request_handler.end_headers()


def client_ip(request_handler) -> str:
    xff = str(request_handler.headers.get("X-Forwarded-For") or "").strip()
    if xff:
        return xff.split(",")[0].strip()
    return str(request_handler.client_address[0] if request_handler.client_address else "unknown")


def is_secure_request(request_handler) -> bool:
    xfp = str(request_handler.headers.get("X-Forwarded-Proto") or "").strip().lower()
    if xfp:
        return xfp == "https"
    forwarded = str(request_handler.headers.get("Forwarded") or "").lower()
    if "proto=https" in forwarded:
        return True
    return bool(getattr(request_handler.server, "server_port", None) == 443)


def read_json_body(request_handler) -> dict[str, Any] | None:
    length = request_handler.headers.get("Content-Length")
    if not length:
        return {}
    try:
        n = int(length)
    except ValueError:
        send_json_response(request_handler, {"error": "invalid_content_length"}, status=HTTPStatus.BAD_REQUEST)
        return None
    if n < 0 or n > 256 * 1024:
        send_json_response(request_handler, {"error": "payload_too_large"}, status=HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
        return None
    raw = request_handler.rfile.read(n)
    if not raw:
        return {}
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception:
        send_json_response(request_handler, {"error": "invalid_json"}, status=HTTPStatus.BAD_REQUEST)
        return None
    if not isinstance(payload, dict):
        send_json_response(request_handler, {"error": "json_must_be_object"}, status=HTTPStatus.BAD_REQUEST)
        return None
    return payload


def send_json_response(request_handler, data: Any, *, status: HTTPStatus = HTTPStatus.OK) -> None:
    encoded = json.dumps(data, ensure_ascii=False).encode("utf-8")
    request_handler.send_response(status)
    request_handler.send_header("Content-Type", "application/json; charset=utf-8")
    if request_handler.path.startswith("/api/"):
        origin = allowed_cors_origin(request_handler)
        if origin is not None:
            request_handler.send_header("Access-Control-Allow-Origin", origin)
            request_handler.send_header("Vary", "Origin")
    request_handler.send_header("Content-Length", str(len(encoded)))
    request_handler.end_headers()
    request_handler.wfile.write(encoded)


def send_text_response(
    request_handler,
    text: str,
    *,
    status: HTTPStatus = HTTPStatus.OK,
    content_type: str = "text/plain; charset=utf-8",
) -> None:
    encoded = text.encode("utf-8")
    request_handler.send_response(status)
    request_handler.send_header("Content-Type", content_type)
    request_handler.send_header("Content-Length", str(len(encoded)))
    request_handler.end_headers()
    request_handler.wfile.write(encoded)


def serve_static_asset(request_handler, filename: str) -> None:
    static_root = resources.files("github_release_watcher").joinpath("static")
    candidate = static_root.joinpath(filename)
    try:
        data = candidate.read_bytes()
    except FileNotFoundError:
        send_text_response(request_handler, "Not found", status=HTTPStatus.NOT_FOUND)
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

    request_handler.send_response(HTTPStatus.OK)
    request_handler.send_header("Content-Type", content_type)
    request_handler.send_header("Cache-Control", "no-store")
    request_handler.send_header("Content-Length", str(len(data)))
    request_handler.end_headers()
    request_handler.wfile.write(data)
