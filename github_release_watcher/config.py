from __future__ import annotations

import logging
import os
import re
try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - fallback for local/dev environments
    import tomli as tomllib  # type: ignore
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config_validation import (
    normalize_asset_type,
    normalize_storage_mode,
    validate_cleanup_mode,
    validate_upload_temp_suffix,
)


class ConfigError(ValueError):
    pass


@dataclass
class GitHubConfig:
    token: str | None = None
    api_base: str = "https://api.github.com"


@dataclass
class WebDAVConfig:
    base_url: str = ""
    username: str | None = None
    password: str | None = None
    verify_tls: bool = True
    timeout_seconds: int = 60
    upload_concurrency: int = 2
    max_retries: int = 3
    retry_backoff_seconds: int = 2
    verify_after_upload: bool = True
    upload_temp_suffix: str = ".uploading"
    cleanup_mode: str = "delete"  # delete | trash


@dataclass
class RepoConfig:
    name: str
    enabled: bool = True
    include_assets: list[str] = field(default_factory=list)
    exclude_assets: list[str] = field(default_factory=list)
    asset_types: list[str] = field(default_factory=list)
    include_prereleases: bool = False
    include_drafts: bool = False
    keep_last: int | None = None


@dataclass
class AppConfig:
    interval_seconds: int = 172800
    download_dir: Path = Path("./downloads")
    state_file: Path = Path("./state.json")
    keep_last: int = 5
    github: GitHubConfig = field(default_factory=GitHubConfig)
    storage_mode: str = "local"  # local | webdav
    webdav: WebDAVConfig = field(default_factory=WebDAVConfig)
    repos: list[RepoConfig] = field(default_factory=list)


def _expand_env_vars(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _expand_env_vars(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env_vars(v) for v in value]
    if isinstance(value, str):
        return os.path.expandvars(value)
    return value


def _as_path(base_dir: Path, raw: Any, field_name: str) -> Path:
    if not isinstance(raw, (str, os.PathLike)):
        raise ConfigError(f"{field_name} must be a path string")
    path = Path(raw)
    if not path.is_absolute():
        path = base_dir / path
    return path


def _normalize_token(raw: Any) -> str | None:
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise ConfigError("github.token must be a string")
    token = raw.strip()
    if not token:
        return None
    if "$" in token:
        return None
    return token


def _compile_regexes(patterns: list[str], field_name: str) -> None:
    for pattern in patterns:
        try:
            re.compile(pattern)
        except re.error as exc:
            raise ConfigError(f"Invalid regex in {field_name}: {pattern!r}: {exc}") from exc


def load_config(path: Path) -> AppConfig:
    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")

    base_dir = path.resolve().parent
    raw_data = tomllib.loads(path.read_text(encoding="utf-8"))
    data = _expand_env_vars(raw_data)

    known_top_level = {"interval_seconds", "download_dir", "state_file", "keep_last", "github", "storage", "repos"}
    for key in data.keys():
        if key not in known_top_level:
            logging.warning("Unknown config key ignored: %s", key)

    config = AppConfig()

    if "interval_seconds" in data:
        config.interval_seconds = int(data["interval_seconds"])
    if "download_dir" in data:
        config.download_dir = _as_path(base_dir, data["download_dir"], "download_dir")
    else:
        config.download_dir = _as_path(base_dir, config.download_dir, "download_dir")
    if "state_file" in data:
        config.state_file = _as_path(base_dir, data["state_file"], "state_file")
    else:
        config.state_file = _as_path(base_dir, config.state_file, "state_file")
    if "keep_last" in data:
        config.keep_last = int(data["keep_last"])

    github = data.get("github", {}) or {}
    if not isinstance(github, dict):
        raise ConfigError("[github] must be a table")
    config.github.api_base = str(github.get("api_base", config.github.api_base))

    config.github.token = _normalize_token(github.get("token"))
    if config.github.token is None:
        config.github.token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GITHUB_OAUTH_TOKEN")

    repos = data.get("repos")
    if repos is None:
        raise ConfigError("Missing [[repos]] in config")
    if not isinstance(repos, list) or not repos:
        raise ConfigError("[[repos]] must be a non-empty list")

    parsed_repos: list[RepoConfig] = []
    for idx, repo_data in enumerate(repos):
        if not isinstance(repo_data, dict):
            raise ConfigError(f"repos[{idx}] must be a table")

        name = repo_data.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ConfigError(f"repos[{idx}].name must be a non-empty string")

        include_assets = repo_data.get("include_assets", []) or []
        exclude_assets = repo_data.get("exclude_assets", []) or []
        asset_types_raw = repo_data.get("asset_types", []) or []
        if not isinstance(include_assets, list) or not all(isinstance(x, str) for x in include_assets):
            raise ConfigError(f"repos[{idx}].include_assets must be a list of strings")
        if not isinstance(exclude_assets, list) or not all(isinstance(x, str) for x in exclude_assets):
            raise ConfigError(f"repos[{idx}].exclude_assets must be a list of strings")
        if not isinstance(asset_types_raw, list) or not all(isinstance(x, str) for x in asset_types_raw):
            raise ConfigError(f"repos[{idx}].asset_types must be a list of strings")

        _compile_regexes(include_assets, f"repos[{idx}].include_assets")
        _compile_regexes(exclude_assets, f"repos[{idx}].exclude_assets")

        asset_types = []
        for value in asset_types_raw:
            try:
                norm = normalize_asset_type(
                    value,
                    empty_message="asset_types items must be non-empty strings",
                    invalid_message=f"asset_types item contains invalid characters: {value!r}",
                )
            except ValueError as exc:
                raise ConfigError(str(exc)) from exc
            if norm not in asset_types:
                asset_types.append(norm)

        keep_last_raw = repo_data.get("keep_last", None)
        keep_last = int(keep_last_raw) if keep_last_raw is not None else None

        repo_cfg = RepoConfig(
            name=name.strip(),
            enabled=bool(repo_data.get("enabled", True)),
            include_assets=include_assets,
            exclude_assets=exclude_assets,
            asset_types=asset_types,
            include_prereleases=bool(repo_data.get("include_prereleases", False)),
            include_drafts=bool(repo_data.get("include_drafts", False)),
            keep_last=keep_last,
        )
        parsed_repos.append(repo_cfg)

    config.repos = parsed_repos

    storage = data.get("storage", {}) or {}
    if storage is not None and not isinstance(storage, dict):
        raise ConfigError("[storage] must be a table")
    if isinstance(storage, dict) and "mode" in storage:
        try:
            config.storage_mode = normalize_storage_mode(storage.get("mode"))
        except ValueError as exc:
            raise ConfigError(str(exc)) from exc

    webdav = storage.get("webdav", {}) if isinstance(storage, dict) else {}
    if webdav is not None and not isinstance(webdav, dict):
        raise ConfigError("[storage.webdav] must be a table")
    if isinstance(webdav, dict):
        if "base_url" in webdav:
            config.webdav.base_url = str(webdav.get("base_url") or "").strip()
        if "username" in webdav:
            raw = webdav.get("username")
            config.webdav.username = str(raw).strip() if isinstance(raw, str) and raw.strip() else None
        if "password" in webdav:
            raw = webdav.get("password")
            config.webdav.password = str(raw) if isinstance(raw, str) else None
        if "verify_tls" in webdav:
            config.webdav.verify_tls = bool(webdav.get("verify_tls", True))
        if "timeout_seconds" in webdav:
            config.webdav.timeout_seconds = int(webdav.get("timeout_seconds") or 60)
        if "upload_concurrency" in webdav:
            config.webdav.upload_concurrency = int(webdav.get("upload_concurrency") or 2)
        if "max_retries" in webdav:
            config.webdav.max_retries = int(webdav.get("max_retries") or 3)
        if "retry_backoff_seconds" in webdav:
            config.webdav.retry_backoff_seconds = int(webdav.get("retry_backoff_seconds") or 2)
        if "verify_after_upload" in webdav:
            config.webdav.verify_after_upload = bool(webdav.get("verify_after_upload", True))
        if "upload_temp_suffix" in webdav:
            config.webdav.upload_temp_suffix = str(webdav.get("upload_temp_suffix") or "").strip()
        if "cleanup_mode" in webdav:
            config.webdav.cleanup_mode = str(webdav.get("cleanup_mode") or "").strip().lower()

    if config.interval_seconds <= 0:
        raise ConfigError("interval_seconds must be > 0")
    if config.keep_last <= 0:
        raise ConfigError("keep_last must be > 0")
    if config.storage_mode == "webdav" and not str(config.webdav.base_url or "").strip():
        raise ConfigError("storage.webdav.base_url is required when storage.mode = 'webdav'")
    if config.webdav.timeout_seconds < 5 or config.webdav.timeout_seconds > 600:
        raise ConfigError("storage.webdav.timeout_seconds must be between 5 and 600")
    if config.webdav.upload_concurrency <= 0 or config.webdav.upload_concurrency > 32:
        raise ConfigError("storage.webdav.upload_concurrency must be between 1 and 32")
    if config.webdav.max_retries <= 0 or config.webdav.max_retries > 20:
        raise ConfigError("storage.webdav.max_retries must be between 1 and 20")
    if config.webdav.retry_backoff_seconds <= 0 or config.webdav.retry_backoff_seconds > 300:
        raise ConfigError("storage.webdav.retry_backoff_seconds must be between 1 and 300")
    try:
        config.webdav.upload_temp_suffix = validate_upload_temp_suffix(config.webdav.upload_temp_suffix)
    except ValueError as exc:
        raise ConfigError(str(exc)) from exc
    try:
        config.webdav.cleanup_mode = validate_cleanup_mode(config.webdav.cleanup_mode)
    except ValueError as exc:
        raise ConfigError(str(exc)) from exc

    for idx, repo_cfg in enumerate(config.repos):
        if repo_cfg.keep_last is not None and repo_cfg.keep_last <= 0:
            raise ConfigError(f"repos[{idx}].keep_last must be > 0 when set")

    return config
