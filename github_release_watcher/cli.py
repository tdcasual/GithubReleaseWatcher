from __future__ import annotations

import argparse
import logging
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
    parser.add_argument("--auth-username", default="admin", help="V2 API login username.")
    parser.add_argument("--auth-password", default="admin", help="V2 API login password.")
    return parser


def _run_web_v2(*, host: str, port: int, log_level: str, db_path: Path, auth_username: str, auth_password: str) -> int:
    from .v2.app import create_app

    app = create_app(db_path=db_path, auth_username=auth_username, auth_password=auth_password)
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

    return _run_web_v2(
        host=str(args.web_host),
        port=int(args.web_port),
        log_level=str(args.log_level).upper(),
        db_path=Path(args.db_path),
        auth_username=str(args.auth_username),
        auth_password=str(args.auth_password),
    )
