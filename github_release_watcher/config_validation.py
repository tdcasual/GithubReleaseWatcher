from __future__ import annotations

import re
from typing import Any


def normalize_storage_mode(raw: Any) -> str:
    mode = str(raw or "").strip().lower()
    if mode in ("", "local"):
        return "local"
    if mode == "webdav":
        return "webdav"
    raise ValueError("storage.mode must be 'local' or 'webdav'")


def normalize_asset_type(
    raw: str,
    *,
    empty_message: str = "asset type is empty",
    invalid_message: str = "asset type has invalid characters",
) -> str:
    value = str(raw or "").strip().lower()
    if value.startswith("."):
        value = value[1:]
    if not value:
        raise ValueError(empty_message)
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,31}", value):
        raise ValueError(invalid_message)
    return value


def validate_upload_temp_suffix(raw: Any) -> str:
    suffix = str(raw or "").strip()
    if not suffix:
        raise ValueError("webdav.upload_temp_suffix must be a non-empty string")
    if "/" in suffix or "\\" in suffix:
        raise ValueError("webdav.upload_temp_suffix cannot contain path separators")
    return suffix


def validate_cleanup_mode(raw: Any) -> str:
    cleanup_mode = str(raw or "").strip().lower()
    if cleanup_mode not in ("delete", "trash"):
        raise ValueError("webdav.cleanup_mode must be 'delete' or 'trash'")
    return cleanup_mode
