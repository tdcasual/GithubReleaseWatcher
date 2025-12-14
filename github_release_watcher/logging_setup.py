from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

DEFAULT_LOG_FILENAME = "watcher.log"


def default_log_path(config_path: Path) -> Path:
    try:
        base = config_path.resolve()
    except Exception:
        base = Path(config_path)
    return base.with_name(DEFAULT_LOG_FILENAME)


def ensure_rotating_file_logging(log_path: Path, *, level: int | None = None) -> None:
    root = logging.getLogger()

    for handler in root.handlers:
        if isinstance(handler, RotatingFileHandler) and getattr(handler, "baseFilename", None) == str(log_path):
            return

    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            log_path,
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        handler.setLevel(level if level is not None else logging.INFO)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        root.addHandler(handler)
    except Exception:
        logging.getLogger(__name__).exception("Failed to set up file logging at %s", log_path)

