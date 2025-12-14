from __future__ import annotations

import time
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

import requests

from .github import Asset


class DownloadError(RuntimeError):
    pass


@dataclass(frozen=True)
class DownloadResult:
    path: Path
    bytes_written: int


class GitHubReleaseAssetDownloader:
    def __init__(
        self,
        github_token: str | None = None,
        timeout_seconds: int = 60,
        max_retries: int = 3,
    ):
        self._token = github_token
        self._timeout = max(5, int(timeout_seconds))
        self._max_retries = max(1, int(max_retries))
        self._session = requests.Session()

    def download_release_asset(self, repo_url: str, tag: str, asset: Asset, dest_dir: Path) -> DownloadResult:
        if Path(asset.name).name != asset.name or ".." in asset.name or "/" in asset.name or "\\" in asset.name:
            raise DownloadError(f"Unsafe asset name: {asset.name!r}")

        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / asset.name

        if dest_path.exists():
            existing_size = int(dest_path.stat().st_size)
            if existing_size > 0:
                expected = asset.size
                if expected is None or expected <= 0:
                    return DownloadResult(path=dest_path, bytes_written=existing_size)
                if existing_size == int(expected):
                    return DownloadResult(path=dest_path, bytes_written=existing_size)

        tmp_path = dest_path.with_suffix(dest_path.suffix + ".part")
        with suppress(FileNotFoundError):
            tmp_path.unlink()

        url, headers = self._choose_download(asset)
        self._download_to_file(url, headers=headers, dest_path=tmp_path, expected_size=asset.size)

        tmp_size = int(tmp_path.stat().st_size) if tmp_path.exists() else 0
        tmp_path.replace(dest_path)
        return DownloadResult(path=dest_path, bytes_written=tmp_size)

    def _choose_download(self, asset: Asset) -> tuple[str, dict[str, str]]:
        headers = {
            "User-Agent": "github-release-watcher",
        }

        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        if asset.api_url:
            headers["Accept"] = "application/octet-stream"
            headers["X-GitHub-Api-Version"] = "2022-11-28"
            return asset.api_url, headers

        # Fallback: public direct download URL.
        return asset.browser_download_url, headers

    def _download_to_file(self, url: str, *, headers: dict[str, str], dest_path: Path, expected_size: int | None) -> None:
        last_exc: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                self._download_once(url, headers=headers, dest_path=dest_path, expected_size=expected_size)
                return
            except DownloadError as exc:
                last_exc = exc
            except requests.RequestException as exc:
                last_exc = exc

            with suppress(FileNotFoundError):
                dest_path.unlink()

            time.sleep(min(2**attempt, 8))

        raise DownloadError(f"Download failed after {self._max_retries} attempts: {last_exc}")

    def _download_once(self, url: str, *, headers: dict[str, str], dest_path: Path, expected_size: int | None) -> None:
        resp = self._session.get(
            url,
            headers=headers,
            stream=True,
            allow_redirects=True,
            timeout=(10, self._timeout),
        )
        try:
            if resp.status_code in (429, 500, 502, 503, 504):
                raise DownloadError(f"transient http {resp.status_code}")
            if resp.status_code != 200:
                raise DownloadError(f"http {resp.status_code}: {resp.text[:500]}")

            dest_path.parent.mkdir(parents=True, exist_ok=True)
            bytes_written = 0
            with dest_path.open("wb") as f:
                for chunk in resp.iter_content(chunk_size=1024 * 256):
                    if not chunk:
                        continue
                    f.write(chunk)
                    bytes_written += len(chunk)

            if expected_size is not None and expected_size >= 0 and bytes_written != expected_size:
                raise DownloadError(f"size mismatch: expected {expected_size}, got {bytes_written}")
        finally:
            resp.close()
