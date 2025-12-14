from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from github_release_watcher.downloader import GitHubReleaseAssetDownloader
from github_release_watcher.github import Asset


class DownloaderBehaviorTests(unittest.TestCase):
    def test_skips_existing_file_when_size_matches(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            dest_dir = Path(td)
            dest_path = dest_dir / "file.bin"
            dest_path.write_bytes(b"abc")

            asset = Asset(id=None, name="file.bin", size=3, browser_download_url="https://example.invalid/file.bin", api_url=None)
            dl = GitHubReleaseAssetDownloader(github_token=None)

            called = {"v": False}

            def fake_download_to_file(url: str, *, headers: dict[str, str], dest_path: Path, expected_size: int | None) -> None:
                called["v"] = True
                raise AssertionError("download should not have been called")

            dl._download_to_file = fake_download_to_file  # type: ignore[method-assign]

            result = dl.download_release_asset("https://github.com/example/repo", "v1", asset, dest_dir)
            self.assertEqual(result.bytes_written, 3)
            self.assertFalse(called["v"])

    def test_redownloads_when_existing_file_size_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            dest_dir = Path(td)
            dest_path = dest_dir / "file.bin"
            dest_path.write_bytes(b"x")

            asset = Asset(id=None, name="file.bin", size=5, browser_download_url="https://example.invalid/file.bin", api_url=None)
            dl = GitHubReleaseAssetDownloader(github_token=None)

            called = {"v": False}

            def fake_download_to_file(url: str, *, headers: dict[str, str], dest_path: Path, expected_size: int | None) -> None:
                called["v"] = True
                n = int(expected_size or 0)
                dest_path.write_bytes(b"y" * n)

            dl._download_to_file = fake_download_to_file  # type: ignore[method-assign]

            result = dl.download_release_asset("https://github.com/example/repo", "v1", asset, dest_dir)
            self.assertTrue(called["v"])
            self.assertEqual(result.bytes_written, 5)
            self.assertEqual(dest_path.stat().st_size, 5)


if __name__ == "__main__":
    unittest.main()

