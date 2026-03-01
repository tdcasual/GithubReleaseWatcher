from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path

from github_release_watcher import watcher
from github_release_watcher.config import AppConfig, GitHubConfig, RepoConfig, WebDAVConfig
from github_release_watcher.github import Asset, Release


class _FakeWebDAV:
    def detect_capabilities(self):
        return {"put": True}


class WatcherWebDAVStatsSafetyTests(unittest.TestCase):
    def test_process_repo_parallel_updates_stats_safely(self) -> None:
        workers = 8
        release_count = 24
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
            for i in range(1, release_count + 1)
        ]

        cfg = AppConfig(
            interval_seconds=60,
            download_dir=Path(tempfile.mkdtemp()) / "downloads",
            state_file=Path(tempfile.mkdtemp()) / "state.json",
            keep_last=release_count,
            github=GitHubConfig(),
            storage_mode="webdav",
            webdav=WebDAVConfig(base_url="https://example.com/dav/", upload_concurrency=workers),
            repos=[RepoConfig(name="owner/repo", keep_last=release_count)],
        )
        repo_cfg = cfg.repos[0]
        state = {"version": 1, "repos": {}}

        wave_barrier = threading.Barrier(workers)

        original_get_recent = watcher._get_recent_releases
        original_ensure = watcher._ensure_release_downloaded_webdav
        original_cleanup = watcher._cleanup_old_releases_webdav

        def fake_get_recent(*args, **kwargs):
            return list(releases)

        def fake_ensure(
            repo_key,
            owner,
            repo,
            repo_https_url,
            cache_repo_dir,
            repo_cfg,
            release,
            downloader,
            webdav,
            repo_state,
            *,
            state_lock=None,
            **kwargs,
        ):
            # Without a lock this intentionally loses updates in each worker wave.
            stats = repo_state.setdefault("stats", {})
            if state_lock is None:
                current = int(stats.get("download_assets_total", 0) or 0)
                try:
                    wave_barrier.wait(timeout=2)
                except threading.BrokenBarrierError:
                    pass
                stats["download_assets_total"] = current + 1
                return True

            with state_lock:
                current = int(stats.get("download_assets_total", 0) or 0)
                stats["download_assets_total"] = current + 1
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

        stats = state.get("repos", {}).get("owner/repo", {}).get("stats", {})
        self.assertTrue(ok)
        self.assertEqual(int(stats.get("download_assets_total", 0) or 0), release_count)


if __name__ == "__main__":
    unittest.main()

