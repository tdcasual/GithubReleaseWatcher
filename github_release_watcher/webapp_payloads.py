from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .config_validation import normalize_asset_type, normalize_storage_mode


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
    return normalize_asset_type(raw)


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


def _resolve_path(base_dir: Path, raw: Any) -> Path:
    if not isinstance(raw, (str, Path)) or not str(raw).strip():
        raise ValueError("path must be a non-empty string")
    p = Path(str(raw).strip())
    return p if p.is_absolute() else (base_dir / p)


def _normalize_storage_mode(raw: Any) -> str:
    return normalize_storage_mode(raw)
