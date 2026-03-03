from __future__ import annotations

from pathlib import Path


def test_legacy_runtime_files_removed() -> None:
    legacy = [
        "github_release_watcher/webapp.py",
        "github_release_watcher/watcher.py",
        "github_release_watcher/webapp_api_router.py",
    ]
    still_exists = [p for p in legacy if Path(p).exists()]
    assert not still_exists
