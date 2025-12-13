from __future__ import annotations

import argparse
import logging
from pathlib import Path

from .config import ConfigError, load_config
from .watcher import run_once, watch_loop


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="github_release_watcher",
        description="Monitor GitHub Releases and back up matching assets via gruntwork-io/fetch.",
    )
    parser.add_argument("--config", type=Path, default=Path("config.toml"), help="Path to config TOML file.")
    parser.add_argument("--once", action="store_true", help="Run a single check and exit.")
    parser.add_argument("--log-level", default="INFO", help="Logging level (e.g. DEBUG, INFO, WARNING).")

    parser.add_argument("--interval-seconds", type=int, default=None, help="Override interval_seconds in config.")
    parser.add_argument("--download-dir", type=Path, default=None, help="Override download_dir in config.")
    parser.add_argument("--state-file", type=Path, default=None, help="Override state_file in config.")
    parser.add_argument("--keep-last", type=int, default=None, help="Override keep_last in config.")
    parser.add_argument("--fetch-path", type=str, default=None, help="Override fetch_path in config.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
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
    if args.fetch_path is not None:
        config.fetch_path = args.fetch_path

    if args.once:
        return run_once(config)
    return watch_loop(config)

