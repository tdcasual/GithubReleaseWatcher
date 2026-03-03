from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .config_validation import validate_cleanup_mode, validate_upload_temp_suffix
from .webapp_overrides import _repo_key_from_spec
from .webapp_payloads import _compile_regex_list, _normalize_asset_types, _normalize_storage_mode, _safe_int


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class SettingsService:
    def apply(self, overrides: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        app_patch = payload.get("app", {}) if isinstance(payload.get("app"), dict) else {}
        if "keep_last" in app_patch:
            overrides.setdefault("app", {})["keep_last"] = _safe_int(app_patch["keep_last"], min_value=1, max_value=1000)
        if "interval_seconds" in app_patch:
            overrides.setdefault("app", {})["interval_seconds"] = _safe_int(
                app_patch["interval_seconds"], min_value=1, max_value=31_536_000
            )

        storage_patch = payload.get("storage", {}) if isinstance(payload.get("storage"), dict) else {}
        if storage_patch:
            storage_store = overrides.setdefault("storage", {})
            if not isinstance(storage_store, dict):
                storage_store = {}
                overrides["storage"] = storage_store

            if "mode" in storage_patch:
                storage_store["mode"] = _normalize_storage_mode(storage_patch.get("mode"))

            if "local_dir" in storage_patch:
                raw = storage_patch.get("local_dir")
                if raw is None:
                    storage_store.pop("local_dir", None)
                elif isinstance(raw, str) and raw.strip():
                    storage_store["local_dir"] = raw.strip()
                else:
                    raise ValueError("storage.local_dir must be a non-empty string or null")

            webdav_patch = storage_patch.get("webdav", {}) if isinstance(storage_patch.get("webdav"), dict) else {}
            if "webdav" in storage_patch:
                webdav_store = storage_store.setdefault("webdav", {})
                if not isinstance(webdav_store, dict):
                    webdav_store = {}
                    storage_store["webdav"] = webdav_store

                if "base_url" in webdav_patch:
                    webdav_store["base_url"] = str(webdav_patch.get("base_url") or "").strip()
                if "username" in webdav_patch:
                    raw_user = webdav_patch.get("username")
                    webdav_store["username"] = str(raw_user).strip() if isinstance(raw_user, str) and raw_user.strip() else None
                if "password" in webdav_patch:
                    raw_pass = webdav_patch.get("password")
                    if raw_pass is None:
                        webdav_store.pop("password", None)
                    elif isinstance(raw_pass, str):
                        if raw_pass != "":
                            webdav_store["password"] = raw_pass
                    else:
                        raise ValueError("webdav.password must be a string or null")
                if "verify_tls" in webdav_patch:
                    webdav_store["verify_tls"] = bool(webdav_patch.get("verify_tls", True))
                if "timeout_seconds" in webdav_patch:
                    webdav_store["timeout_seconds"] = _safe_int(
                        webdav_patch.get("timeout_seconds"), min_value=5, max_value=600
                    )
                if "upload_concurrency" in webdav_patch:
                    webdav_store["upload_concurrency"] = _safe_int(
                        webdav_patch.get("upload_concurrency"), min_value=1, max_value=32
                    )
                if "max_retries" in webdav_patch:
                    webdav_store["max_retries"] = _safe_int(webdav_patch.get("max_retries"), min_value=1, max_value=20)
                if "retry_backoff_seconds" in webdav_patch:
                    webdav_store["retry_backoff_seconds"] = _safe_int(
                        webdav_patch.get("retry_backoff_seconds"), min_value=1, max_value=300
                    )
                if "verify_after_upload" in webdav_patch:
                    webdav_store["verify_after_upload"] = bool(webdav_patch.get("verify_after_upload", True))
                if "upload_temp_suffix" in webdav_patch:
                    webdav_store["upload_temp_suffix"] = validate_upload_temp_suffix(webdav_patch.get("upload_temp_suffix"))
                if "cleanup_mode" in webdav_patch:
                    webdav_store["cleanup_mode"] = validate_cleanup_mode(webdav_patch.get("cleanup_mode"))

            mode_effective = _normalize_storage_mode(storage_store.get("mode"))
            if mode_effective == "webdav":
                webdav_store = storage_store.get("webdav", {})
                if not isinstance(webdav_store, dict):
                    raise ValueError("storage.webdav must be an object")
                base_url = str(webdav_store.get("base_url") or "").strip()
                if not base_url:
                    raise ValueError("webdav.base_url is required when storage.mode = 'webdav'")

        repos_patch = payload.get("repos", {}) if isinstance(payload.get("repos"), dict) else {}
        if repos_patch:
            repos_store = overrides.setdefault("repos", {})
            if not isinstance(repos_store, dict):
                repos_store = {}
                overrides["repos"] = repos_store

            for key, patch in repos_patch.items():
                if not isinstance(patch, dict):
                    continue
                spec = str(patch.get("name") or key)
                normalized_key = _repo_key_from_spec(spec)

                current = repos_store.get(normalized_key, {}) if isinstance(repos_store.get(normalized_key), dict) else {}
                updated = dict(current)
                updated["name"] = spec

                if "enabled" in patch:
                    updated["enabled"] = bool(patch["enabled"])
                if "keep_last" in patch:
                    raw_keep_last = patch["keep_last"]
                    updated["keep_last"] = None if raw_keep_last is None else _safe_int(raw_keep_last, min_value=1, max_value=1000)
                if "asset_types" in patch:
                    updated["asset_types"] = _normalize_asset_types(patch["asset_types"])
                if "include_assets" in patch:
                    updated["include_assets"] = _compile_regex_list(patch["include_assets"], "include_assets")
                if "exclude_assets" in patch:
                    updated["exclude_assets"] = _compile_regex_list(patch["exclude_assets"], "exclude_assets")
                if "include_prereleases" in patch:
                    updated["include_prereleases"] = bool(patch["include_prereleases"])
                if "include_drafts" in patch:
                    updated["include_drafts"] = bool(patch["include_drafts"])

                repos_store[normalized_key] = updated

        overrides["updated_at"] = _utc_now_iso()
        return overrides
