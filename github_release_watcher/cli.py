from __future__ import annotations

import argparse
import logging
from pathlib import Path

from .config import ConfigError, load_config
from .logging_setup import default_log_path, ensure_rotating_file_logging
from .watcher import run_once, watch_loop


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="github_release_watcher",
        description="Monitor GitHub Releases and back up matching assets (pure Python).",
    )
    parser.add_argument("--config", type=Path, default=Path("config.toml"), help="Path to config TOML file.")
    parser.add_argument("--once", action="store_true", help="Run a single check and exit.")
    parser.add_argument("--log-level", default="INFO", help="Logging level (e.g. DEBUG, INFO, WARNING).")

    parser.add_argument("--web", action="store_true", help="Start built-in web API server (and optional UI).")
    parser.add_argument("--web-v2", action="store_true", help="Start V2 FastAPI server.")
    parser.add_argument("--web-host", default="127.0.0.1", help="Web server bind host (default: 127.0.0.1).")
    parser.add_argument("--web-port", type=int, default=8000, help="Web server port (default: 8000).")
    parser.add_argument("--no-ui", action="store_true", help="Disable the built-in web UI (API still available).")
    parser.add_argument("--web-no-scheduler", action="store_true", help="Do not start the periodic scheduler at startup.")

    parser.add_argument("--interval-seconds", type=int, default=None, help="Override interval_seconds in config.")
    parser.add_argument("--download-dir", type=Path, default=None, help="Override download_dir in config.")
    parser.add_argument("--state-file", type=Path, default=None, help="Override state_file in config.")
    parser.add_argument("--keep-last", type=int, default=None, help="Override keep_last in config.")
    return parser


def _run_web_v2(*, host: str, port: int, log_level: str) -> int:
    from .v2.app import create_app

    app = create_app()
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
    ensure_rotating_file_logging(default_log_path(args.config), level=getattr(logging, str(args.log_level).upper(), logging.INFO))

    if args.web_v2:
        return _run_web_v2(
            host=str(args.web_host),
            port=int(args.web_port),
            log_level=str(args.log_level).upper(),
        )

    if args.web:
        from .webapp import serve

        scheduler_enabled = not args.web_no_scheduler
        run_immediately = bool(args.once or scheduler_enabled)
        return serve(
            config_path=args.config,
            log_file=default_log_path(args.config),
            host=str(args.web_host),
            port=int(args.web_port),
            ui=not args.no_ui,
            scheduler_enabled=scheduler_enabled,
            run_immediately=run_immediately,
        )

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        logging.error("Config error: %s", exc)
        return 2

    if args.interval_seconds is not None:
        config.interval_seconds = args.interval_seconds
    if args.download_dir is not None:
        config.download_dir = args.download_dir
    if args.state_file is not None:
        config.state_file = args.state_file
    if args.keep_last is not None:
        config.keep_last = args.keep_last

    if args.once:
        return run_once(config)
    return watch_loop(config)
