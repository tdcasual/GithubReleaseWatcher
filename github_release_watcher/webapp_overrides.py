from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import AppConfig, RepoConfig, WebDAVConfig
from .config_validation import validate_cleanup_mode, validate_upload_temp_suffix
from .github import parse_repo_spec
from .webapp_payloads import _compile_regex_list, _normalize_asset_types, _normalize_storage_mode, _resolve_path, _safe_int


def _repo_key_from_spec(spec: str) -> str:
    owner, repo, _ = parse_repo_spec(spec)
    return f"{owner}/{repo}"


def _apply_overrides(config: AppConfig, overrides: dict[str, Any], *, base_dir: Path) -> None:
    app_overrides = overrides.get("app", {}) if isinstance(overrides.get("app"), dict) else {}
    if "keep_last" in app_overrides:
        config.keep_last = _safe_int(app_overrides["keep_last"], min_value=1, max_value=1000)
    if "interval_seconds" in app_overrides:
        config.interval_seconds = _safe_int(app_overrides["interval_seconds"], min_value=1, max_value=31_536_000)

    storage_overrides = overrides.get("storage", {}) if isinstance(overrides.get("storage"), dict) else {}
    if storage_overrides:
        if "local_dir" in storage_overrides:
            config.download_dir = _resolve_path(base_dir, storage_overrides.get("local_dir"))

        if "mode" in storage_overrides:
            config.storage_mode = _normalize_storage_mode(storage_overrides.get("mode"))

        webdav_overrides = storage_overrides.get("webdav", {}) if isinstance(storage_overrides.get("webdav"), dict) else {}
        if webdav_overrides:
            if not hasattr(config, "webdav") or not isinstance(getattr(config, "webdav"), WebDAVConfig):
                config.webdav = WebDAVConfig()
            if "base_url" in webdav_overrides:
                config.webdav.base_url = str(webdav_overrides.get("base_url") or "").strip()
            if "username" in webdav_overrides:
                raw_user = webdav_overrides.get("username")
                config.webdav.username = str(raw_user).strip() if isinstance(raw_user, str) and raw_user.strip() else None
            if "password" in webdav_overrides:
                raw_pass = webdav_overrides.get("password")
                config.webdav.password = str(raw_pass) if isinstance(raw_pass, str) and raw_pass else None
            if "verify_tls" in webdav_overrides:
                config.webdav.verify_tls = bool(webdav_overrides.get("verify_tls", True))
            if "timeout_seconds" in webdav_overrides:
                config.webdav.timeout_seconds = _safe_int(webdav_overrides.get("timeout_seconds"), min_value=5, max_value=600)
            if "upload_concurrency" in webdav_overrides:
                config.webdav.upload_concurrency = _safe_int(webdav_overrides.get("upload_concurrency"), min_value=1, max_value=32)
            if "max_retries" in webdav_overrides:
                config.webdav.max_retries = _safe_int(webdav_overrides.get("max_retries"), min_value=1, max_value=20)
            if "retry_backoff_seconds" in webdav_overrides:
                config.webdav.retry_backoff_seconds = _safe_int(
                    webdav_overrides.get("retry_backoff_seconds"), min_value=1, max_value=300
                )
            if "verify_after_upload" in webdav_overrides:
                config.webdav.verify_after_upload = bool(webdav_overrides.get("verify_after_upload", True))
            if "upload_temp_suffix" in webdav_overrides:
                config.webdav.upload_temp_suffix = validate_upload_temp_suffix(webdav_overrides.get("upload_temp_suffix"))
            if "cleanup_mode" in webdav_overrides:
                config.webdav.cleanup_mode = validate_cleanup_mode(webdav_overrides.get("cleanup_mode"))

        if str(getattr(config, "storage_mode", "local") or "local") == "webdav":
            if not str(getattr(getattr(config, "webdav", None), "base_url", "") or "").strip():
                raise ValueError("webdav.base_url is required when storage.mode = 'webdav'")

    repo_overrides = overrides.get("repos", {}) if isinstance(overrides.get("repos"), dict) else {}

    by_key: dict[str, RepoConfig] = {}
    for repo_cfg in config.repos:
        try:
            by_key[_repo_key_from_spec(repo_cfg.name)] = repo_cfg
        except Exception:
            by_key[repo_cfg.name] = repo_cfg

    for key, patch in repo_overrides.items():
        if not isinstance(key, str) or not isinstance(patch, dict):
            continue

        repo_cfg = by_key.get(key)
        if repo_cfg is None:
            name = str(patch.get("name") or key)
            repo_cfg = RepoConfig(name=name)
            config.repos.append(repo_cfg)
            by_key[key] = repo_cfg

        if "enabled" in patch:
            repo_cfg.enabled = bool(patch["enabled"])
        if "keep_last" in patch:
            raw_keep_last = patch["keep_last"]
            repo_cfg.keep_last = None if raw_keep_last is None else _safe_int(raw_keep_last, min_value=1, max_value=1000)
        if "asset_types" in patch:
            repo_cfg.asset_types = _normalize_asset_types(patch["asset_types"])
        if "include_assets" in patch:
            repo_cfg.include_assets = _compile_regex_list(patch["include_assets"], "include_assets")
        if "exclude_assets" in patch:
            repo_cfg.exclude_assets = _compile_regex_list(patch["exclude_assets"], "exclude_assets")
        if "include_prereleases" in patch:
            repo_cfg.include_prereleases = bool(patch["include_prereleases"])
        if "include_drafts" in patch:
            repo_cfg.include_drafts = bool(patch["include_drafts"])
