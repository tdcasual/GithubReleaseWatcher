from __future__ import annotations

from pathlib import Path


def test_legacy_runtime_files_removed() -> None:
    legacy = [
        "github_release_watcher/webapp.py",
        "github_release_watcher/watcher.py",
        "github_release_watcher/webapp_api_router.py",
        "github_release_watcher/config.py",
        "github_release_watcher/config_validation.py",
        "github_release_watcher/downloader.py",
        "github_release_watcher/github.py",
        "github_release_watcher/webdav.py",
        "github_release_watcher/metrics.py",
        "github_release_watcher/logging_setup.py",
    ]
    still_exists = [p for p in legacy if Path(p).exists()]
    assert not still_exists
