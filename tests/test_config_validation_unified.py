from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from github_release_watcher.config import ConfigError, load_config
from github_release_watcher.config_validation import (
    normalize_asset_type,
    normalize_storage_mode,
    validate_cleanup_mode,
    validate_upload_temp_suffix,
)
from github_release_watcher.settings_service import SettingsService
from github_release_watcher.webapp_overrides import _apply_overrides


def test_shared_validation_helpers_cover_common_rules() -> None:
    assert normalize_storage_mode("webdav") == "webdav"
    assert normalize_storage_mode("LOCAL") == "local"
    assert normalize_storage_mode("") == "local"
    assert normalize_asset_type(".ZIP") == "zip"
    assert validate_upload_temp_suffix(".uploading") == ".uploading"
    assert validate_cleanup_mode("trash") == "trash"

    with pytest.raises(ValueError):
        normalize_storage_mode("s3")
    with pytest.raises(ValueError):
        normalize_asset_type("bad/type")
    with pytest.raises(ValueError):
        validate_upload_temp_suffix("a/b")
    with pytest.raises(ValueError):
        validate_cleanup_mode("archive")


def test_settings_and_overrides_reject_webdav_suffix_with_path_separator() -> None:
    overrides = {"version": 1, "updated_at": "2026-01-01T00:00:00+00:00", "app": {}, "repos": {}, "auth": {}, "storage": {}}
    payload = {"storage": {"webdav": {"upload_temp_suffix": "bad/suffix"}}}
    svc = SettingsService()
    with pytest.raises(ValueError, match="upload_temp_suffix"):
        svc.apply(overrides, payload)

    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        cfg_path = base / "config.toml"
        cfg_path.write_text(
            "\n".join(
                [
                    "interval_seconds = 60",
                    'download_dir = "./downloads"',
                    'state_file = "./state.json"',
                    "keep_last = 1",
                    "",
                    "[[repos]]",
                    'name = "owner/repo"',
                    "",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        cfg = load_config(cfg_path)
        with pytest.raises(ValueError, match="upload_temp_suffix"):
            _apply_overrides(
                cfg,
                {"storage": {"webdav": {"upload_temp_suffix": "bad\\suffix"}}},
                base_dir=base,
            )


def test_load_config_enforces_webdav_timeout_range_like_settings() -> None:
    with tempfile.TemporaryDirectory() as td:
        cfg_path = Path(td) / "config.toml"
        cfg_path.write_text(
            "\n".join(
                [
                    "interval_seconds = 60",
                    'download_dir = "./downloads"',
                    'state_file = "./state.json"',
                    "keep_last = 1",
                    "",
                    "[storage]",
                    'mode = "webdav"',
                    "",
                    "[storage.webdav]",
                    'base_url = "https://example.com/dav/"',
                    "timeout_seconds = 1",
                    "",
                    "[[repos]]",
                    'name = "owner/repo"',
                    "",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        with pytest.raises(ConfigError, match="timeout_seconds"):
            load_config(cfg_path)
