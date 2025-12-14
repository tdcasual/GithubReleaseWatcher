from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from github_release_watcher.config import load_config
from github_release_watcher.downloader import GitHubReleaseAssetDownloader
from github_release_watcher.github import GitHubClient
from github_release_watcher.watcher import run_once


class DownloadIntegrationTests(unittest.TestCase):
    def _token(self) -> str | None:
        return os.environ.get("GITHUB_TOKEN") or os.environ.get("GITHUB_OAUTH_TOKEN")

    def test_downloader_can_download_small_release_asset(self) -> None:
        github = GitHubClient(token=self._token())
        releases = github.list_releases("gruntwork-io", "fetch", per_page=30, max_pages=2)
        self.assertTrue(releases, "Expected at least one release")

        chosen = None
        chosen_asset = None
        for r in releases:
            for a in r.assets:
                if a.name == "SHA256SUMS":
                    chosen = r
                    chosen_asset = a
                    break
            if chosen_asset:
                break

        self.assertIsNotNone(chosen_asset, "Expected to find SHA256SUMS asset in recent releases")

        with tempfile.TemporaryDirectory() as td:
            dest_dir = Path(td)
            dl = GitHubReleaseAssetDownloader(github_token=self._token(), timeout_seconds=60, max_retries=3)
            result = dl.download_release_asset("https://github.com/gruntwork-io/fetch", chosen.tag_name, chosen_asset, dest_dir)

            self.assertTrue(result.path.exists())
            self.assertGreater(result.bytes_written, 0)
            self.assertEqual(result.path.name, "SHA256SUMS")

    def test_run_once_downloads_and_records_state(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            cfg_path = base / "config.toml"
            cfg_path.write_text(
                "\n".join(
                    [
                        "interval_seconds = 600",
                        'download_dir = "./downloads"',
                        'state_file = "./state.json"',
                        "keep_last = 1",
                        "",
                        "[github]",
                        'token = ""',
                        "",
                        "[[repos]]",
                        'name = "gruntwork-io/fetch"',
                        'include_assets = ["^SHA256SUMS$"]',
                        "exclude_assets = []",
                        "asset_types = []",
                        "include_prereleases = false",
                        "include_drafts = false",
                        "keep_last = 1",
                        "",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            cfg = load_config(cfg_path)
            if self._token():
                cfg.github.token = self._token()

            exit_code = run_once(cfg)
            self.assertEqual(exit_code, 0, "Expected run_once to succeed")

            # Find downloaded release folder and asset.
            repo_root = cfg.download_dir / "gruntwork-io" / "fetch"
            self.assertTrue(repo_root.exists(), "Expected repo directory to exist")
            tags = [p for p in repo_root.iterdir() if p.is_dir()]
            self.assertEqual(len(tags), 1, "Expected exactly one kept release directory")

            tag_dir = tags[0]
            self.assertTrue((tag_dir / "release.json").exists(), "Expected release.json metadata to be written")
            self.assertTrue((tag_dir / "SHA256SUMS").exists(), "Expected SHA256SUMS to be downloaded")
            self.assertGreater((tag_dir / "SHA256SUMS").stat().st_size, 0)

            state = json.loads(cfg.state_file.read_text(encoding="utf-8"))
            self.assertIn("repos", state)
            self.assertIn("gruntwork-io/fetch", state["repos"])


if __name__ == "__main__":
    unittest.main()

