from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path


class DownloadError(RuntimeError):
    pass


class FetchDownloader:
    def __init__(self, fetch_path: str = "fetch", github_token: str | None = None):
        self._fetch_path = fetch_path
        self._github_token = github_token

    def download_release_asset(self, repo_url: str, tag: str, asset_name: str, dest_dir: Path) -> None:
        dest_dir.mkdir(parents=True, exist_ok=True)

        asset_regex = f"^{re.escape(asset_name)}$"
        cmd = [
            self._fetch_path,
            f"--repo={repo_url}",
            f"--tag={tag}",
            f"--release-asset={asset_regex}",
            str(dest_dir),
        ]

        env = os.environ.copy()
        if self._github_token:
            env.setdefault("GITHUB_OAUTH_TOKEN", self._github_token)

        try:
            subprocess.run(cmd, env=env, check=True)
        except FileNotFoundError as exc:
            raise DownloadError(
                f"fetch not found: {self._fetch_path!r}. Install from https://github.com/gruntwork-io/fetch/releases"
            ) from exc
        except subprocess.CalledProcessError as exc:
            raise DownloadError(f"fetch failed with exit code {exc.returncode}: {' '.join(cmd)}") from exc

