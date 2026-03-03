from __future__ import annotations

import pytest

from github_release_watcher.settings_service import SettingsService


def test_settings_service_rejects_webdav_without_base_url() -> None:
    svc = SettingsService()
    overrides = {"version": 1, "updated_at": "2026-01-01T00:00:00+00:00", "app": {}, "repos": {}, "auth": {}, "storage": {}}
    payload = {"storage": {"mode": "webdav", "webdav": {"base_url": ""}}}

    with pytest.raises(ValueError, match="webdav.base_url"):
        svc.apply(overrides, payload)
