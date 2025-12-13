from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import time
from typing import Any
from urllib.parse import urlparse

import requests


class GitHubApiError(RuntimeError):
    pass


def _parse_iso8601(value: str | None) -> datetime | None:
    if not value:
        return None
    # GitHub timestamps are typically like "2025-01-01T12:34:56Z"
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


@dataclass(frozen=True)
class Asset:
    name: str
    size: int | None
    browser_download_url: str


@dataclass(frozen=True)
class Release:
    tag_name: str
    draft: bool
    prerelease: bool
    created_at: datetime | None
    published_at: datetime | None
    html_url: str | None
    assets: list[Asset]


def parse_repo(name: str) -> tuple[str, str]:
    owner, repo, _ = parse_repo_spec(name)
    return owner, repo


def parse_repo_spec(name: str) -> tuple[str, str, str]:
    raw = name.strip()
    if not raw:
        raise ValueError("repo name is empty")

    if raw.startswith(("http://", "https://")):
        parsed = urlparse(raw)
        path = parsed.path.strip("/")
        parts = [p for p in path.split("/") if p]
        if len(parts) < 2:
            raise ValueError(f"invalid GitHub repo URL: {name!r}")
        owner, repo = parts[0], parts[1]
        base = f"{parsed.scheme}://{parsed.netloc}"
    elif raw.startswith("git@"):
        # git@github.com:owner/repo.git
        host_part = raw.split(":", 1)[0]  # git@github.com
        host = host_part.split("@", 1)[-1]
        after_colon = raw.split(":", 1)[-1]
        parts = [p for p in after_colon.split("/") if p]
        if len(parts) < 2:
            raise ValueError(f"invalid GitHub repo spec: {name!r}")
        owner, repo = parts[0], parts[1]
        base = f"https://{host}"
    else:
        parts = [p for p in raw.split("/") if p]
        if len(parts) != 2:
            raise ValueError(f"repo must be in 'owner/repo' format: {name!r}")
        owner, repo = parts[0], parts[1]
        base = "https://github.com"

    if repo.endswith(".git"):
        repo = repo[: -len(".git")]
    if not owner or not repo:
        raise ValueError(f"invalid repo: {name!r}")

    return owner, repo, f"{base}/{owner}/{repo}"


def repo_url(owner: str, repo: str) -> str:
    return f"https://github.com/{owner}/{repo}"


class GitHubClient:
    def __init__(self, api_base: str = "https://api.github.com", token: str | None = None, timeout_seconds: int = 30):
        self._api_base = api_base.rstrip("/")
        self._token = token
        self._timeout = timeout_seconds
        self._session = requests.Session()

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "github-release-watcher",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def _get_json(self, url: str, params: dict[str, Any]) -> Any:
        last_exc: Exception | None = None
        for attempt in range(1, 4):
            try:
                resp = self._session.get(
                    url,
                    headers=self._headers(),
                    params=params,
                    timeout=self._timeout,
                )
            except requests.RequestException as exc:
                last_exc = exc
                time.sleep(min(2**attempt, 8))
                continue

            if resp.status_code in (429, 500, 502, 503, 504):
                time.sleep(min(2**attempt, 8))
                continue

            if resp.status_code != 200:
                raise GitHubApiError(f"GitHub API error {resp.status_code}: {resp.text}")

            return resp.json()

        raise GitHubApiError(f"GitHub API request failed after retries: {last_exc}")

    def list_releases(self, owner: str, repo: str, per_page: int = 30, max_pages: int = 5) -> list[Release]:
        releases: list[Release] = []
        per_page = max(1, min(int(per_page), 100))

        for page in range(1, max_pages + 1):
            url = f"{self._api_base}/repos/{owner}/{repo}/releases"
            payload = self._get_json(url, params={"per_page": per_page, "page": page})
            if not isinstance(payload, list):
                raise GitHubApiError(f"Unexpected GitHub API response for {owner}/{repo}: {payload!r}")
            if not payload:
                break

            for item in payload:
                releases.append(_parse_release(item))

            if len(payload) < per_page:
                break

        return releases


def _parse_release(item: Any) -> Release:
    if not isinstance(item, dict):
        raise GitHubApiError(f"Unexpected release payload: {item!r}")

    assets_payload = item.get("assets") or []
    assets: list[Asset] = []
    if isinstance(assets_payload, list):
        for a in assets_payload:
            if not isinstance(a, dict):
                continue
            name = a.get("name")
            url = a.get("browser_download_url")
            if isinstance(name, str) and isinstance(url, str):
                size = a.get("size")
                assets.append(Asset(name=name, size=int(size) if isinstance(size, int) else None, browser_download_url=url))

    return Release(
        tag_name=str(item.get("tag_name") or ""),
        draft=bool(item.get("draft", False)),
        prerelease=bool(item.get("prerelease", False)),
        created_at=_parse_iso8601(item.get("created_at")),
        published_at=_parse_iso8601(item.get("published_at")),
        html_url=item.get("html_url") if isinstance(item.get("html_url"), str) else None,
        assets=assets,
    )
