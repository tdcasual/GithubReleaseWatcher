from __future__ import annotations

import tempfile
import threading
import time
import unittest
from pathlib import Path

from github_release_watcher.config import AppConfig, GitHubConfig, RepoConfig, WebDAVConfig
from github_release_watcher.github import Asset, Release
from github_release_watcher import watcher


class _FakeWebDAV:
    def detect_capabilities(self):
        return {"put": True}


class WatcherWebDAVParallelTests(unittest.TestCase):
    def test_process_repo_uses_webdav_upload_concurrency(self) -> None:
        releases = [
            Release(
                tag_name=f"v{i}",
                draft=False,
                prerelease=False,
                created_at=None,
                published_at=None,
                html_url=None,
                assets=[Asset(id=i, name=f"a{i}.bin", size=1, browser_download_url="https://example.com", api_url=None)],
            )
            for i in range(1, 5)
        ]

        cfg = AppConfig(
            interval_seconds=60,
            download_dir=Path(tempfile.mkdtemp()) / "downloads",
            state_file=Path(tempfile.mkdtemp()) / "state.json",
            keep_last=4,
            github=GitHubConfig(),
            storage_mode="webdav",
            webdav=WebDAVConfig(base_url="https://example.com/dav/", upload_concurrency=3),
            repos=[RepoConfig(name="owner/repo", keep_last=4)],
        )
        repo_cfg = cfg.repos[0]
        state = {"version": 1, "repos": {}}

        lock = threading.Lock()
        active = 0
        peak = 0

        original_get_recent = watcher._get_recent_releases
        original_ensure = watcher._ensure_release_downloaded_webdav
        original_cleanup = watcher._cleanup_old_releases_webdav

        def fake_get_recent(*args, **kwargs):
            return list(releases)

        def fake_ensure(*args, **kwargs):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.05)
            with lock:
                active -= 1
            return True

        def fake_cleanup(*args, **kwargs):
            return None

        watcher._get_recent_releases = fake_get_recent
        watcher._ensure_release_downloaded_webdav = fake_ensure
        watcher._cleanup_old_releases_webdav = fake_cleanup
        try:
            ok = watcher._process_repo(
                cfg,
                repo_cfg,
                github=object(),
                downloader=object(),
                state=state,
                webdav=_FakeWebDAV(),
            )
        finally:
            watcher._get_recent_releases = original_get_recent
            watcher._ensure_release_downloaded_webdav = original_ensure
            watcher._cleanup_old_releases_webdav = original_cleanup

        self.assertTrue(ok)
        self.assertGreaterEqual(peak, 2)


if __name__ == "__main__":
    unittest.main()
