from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="github_release_watcher",
        description="Run GitHub Release Watcher V2 API server.",
    )
    parser.add_argument("--web", action="store_true", help="Start V2 FastAPI server.")
    parser.add_argument("--web-host", default="127.0.0.1", help="Web server bind host (default: 127.0.0.1).")
    parser.add_argument("--web-port", type=int, default=8000, help="Web server port (default: 8000).")
    parser.add_argument("--log-level", default="INFO", help="Logging level (e.g. DEBUG, INFO, WARNING).")
    parser.add_argument("--db-path", type=Path, default=Path("v2.sqlite3"), help="Path to V2 sqlite database file.")
    parser.add_argument("--auth-username", default=None, help="V2 API login username (or GRW_AUTH_USERNAME).")
    parser.add_argument("--auth-password", default=None, help="V2 API login password (or GRW_AUTH_PASSWORD).")
    parser.add_argument(
        "--insecure-cookie",
        action="store_true",
        help="Disable Secure attribute for session cookie (local HTTP only).",
    )
    return parser


def _resolve_auth_credentials(raw_username: str | None, raw_password: str | None) -> tuple[str, str] | None:
    username = str(raw_username or os.environ.get("GRW_AUTH_USERNAME") or "").strip()
    password = str(raw_password or os.environ.get("GRW_AUTH_PASSWORD") or "")
    if not username or not password:
        return None
    return username, password


def _run_web_v2(
    *,
    host: str,
    port: int,
    log_level: str,
    db_path: Path,
    auth_username: str,
    auth_password: str,
    session_cookie_secure: bool,
) -> int:
    from .v2.app import create_app

    app = create_app(
        db_path=db_path,
        auth_username=auth_username,
        auth_password=auth_password,
        session_cookie_secure=session_cookie_secure,
    )
    try:
        import uvicorn  # type: ignore
    except Exception as exc:
        logging.error("V2 web server requires uvicorn: %s", exc)
        return 2

    uvicorn.run(app, host=str(host), port=int(port), log_level=str(log_level).lower())
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
    )

    if not args.web:
        logging.error("V2 hard-cut mode only supports --web")
        return 2

    creds = _resolve_auth_credentials(args.auth_username, args.auth_password)
    if creds is None:
        logging.error("auth credentials are required: set --auth-username/--auth-password or GRW_AUTH_* env vars")
        return 2
    auth_username, auth_password = creds

    return _run_web_v2(
        host=str(args.web_host),
        port=int(args.web_port),
        log_level=str(args.log_level).upper(),
        db_path=Path(args.db_path),
        auth_username=auth_username,
        auth_password=auth_password,
        session_cookie_secure=not bool(args.insecure_cookie),
    )
