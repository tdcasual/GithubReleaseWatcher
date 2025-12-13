from __future__ import annotations

import json
import logging
import re
import shutil
import time
from pathlib import Path
from typing import Iterable

from .config import AppConfig, RepoConfig
from .downloader import DownloadError, FetchDownloader
from .github import GitHubApiError, GitHubClient, Release, parse_repo_spec
from .state import get_repo_state, load_state, mark_release_processed, remove_release_state, save_state


def watch_loop(config: AppConfig) -> int:
    while True:
        exit_code = run_once(config)
        if exit_code != 0:
            logging.warning("Run finished with errors; will retry after %ss", config.interval_seconds)
        try:
            time.sleep(config.interval_seconds)
        except KeyboardInterrupt:
            logging.info("Interrupted.")
            return exit_code


def run_once(config: AppConfig) -> int:
    state = load_state(config.state_file)
    github = GitHubClient(api_base=config.github.api_base, token=config.github.token)
    downloader = FetchDownloader(fetch_path=config.fetch_path, github_token=config.github.token)

    had_errors = False
    for repo_cfg in config.repos:
        try:
            ok = _process_repo(config, repo_cfg, github, downloader, state)
            had_errors = had_errors or not ok
        except Exception:
            logging.exception("Failed processing repo %s", repo_cfg.name)
            had_errors = True

    save_state(config.state_file, state)
    return 1 if had_errors else 0


def _process_repo(
    config: AppConfig,
    repo_cfg: RepoConfig,
    github: GitHubClient,
    downloader: FetchDownloader,
    state: dict,
) -> bool:
    owner, repo, repo_https_url = parse_repo_spec(repo_cfg.name)
    repo_key = f"{owner}/{repo}"
    keep_last = repo_cfg.keep_last or config.keep_last

    releases = _get_recent_releases(github, owner, repo, keep_last, repo_cfg)
    if not releases:
        logging.info("[%s] No releases found (after filtering).", repo_key)
        return True

    releases.sort(key=_release_sort_key, reverse=True)
    wanted = releases[:keep_last]
    wanted_tags = [r.tag_name for r in wanted if r.tag_name]

    repo_dir = config.download_dir / owner / repo
    repo_dir.mkdir(parents=True, exist_ok=True)

    repo_state = get_repo_state(state, repo_key)

    ok = True
    for release in reversed(wanted):
        ok = _ensure_release_downloaded(repo_key, repo_https_url, repo_dir, repo_cfg, release, downloader, repo_state) and ok

    _cleanup_old_releases(repo_key, repo_dir, wanted_tags, repo_state)
    return ok


def _get_recent_releases(
    github: GitHubClient,
    owner: str,
    repo: str,
    keep_last: int,
    repo_cfg: RepoConfig,
) -> list[Release]:
    # Fetch extra to account for drafts/prereleases filtering
    per_page = min(max(keep_last * 3, 30), 100)
    max_pages = 10

    try:
        all_releases = github.list_releases(owner, repo, per_page=per_page, max_pages=max_pages)
    except GitHubApiError:
        raise

    filtered: list[Release] = []
    for r in all_releases:
        if not repo_cfg.include_drafts and r.draft:
            continue
        if not repo_cfg.include_prereleases and r.prerelease:
            continue
        if not r.tag_name:
            continue
        filtered.append(r)
        if len(filtered) >= keep_last:
            # We may still want to fetch a bit more in case of sorting ties,
            # but the list returned by GitHub is already sorted by created desc.
            pass

    return filtered


def _release_sort_key(release: Release):
    # Prefer published_at; fall back to created_at; finally tag string
    return release.published_at or release.created_at, release.tag_name


def _sanitize_path_component(value: str) -> str:
    value = value.strip()
    value = value.replace("/", "__").replace("\\", "__")
    value = value.replace("..", "__")
    return value or "__empty__"


def _is_safe_filename(name: str) -> bool:
    # GitHub asset names should be filenames, but guard against traversal.
    p = Path(name)
    return p.name == name and ".." not in name and "/" not in name and "\\" not in name


def _compile_patterns(patterns: Iterable[str]) -> list[re.Pattern[str]]:
    compiled: list[re.Pattern[str]] = []
    for pattern in patterns:
        compiled.append(re.compile(pattern))
    return compiled


def _select_assets(release: Release, repo_cfg: RepoConfig) -> list[str]:
    include = _compile_patterns(repo_cfg.include_assets)
    exclude = _compile_patterns(repo_cfg.exclude_assets)

    selected: list[str] = []
    for asset in release.assets:
        name = asset.name
        if not _is_safe_filename(name):
            continue

        if include and not any(p.search(name) for p in include):
            continue
        if exclude and any(p.search(name) for p in exclude):
            continue
        selected.append(name)
    return selected


def _ensure_release_downloaded(
    repo_key: str,
    repo_https_url: str,
    repo_dir: Path,
    repo_cfg: RepoConfig,
    release: Release,
    downloader: FetchDownloader,
    repo_state: dict,
) -> bool:
    tag = release.tag_name
    tag_dir = repo_dir / _sanitize_path_component(tag)
    tag_dir.mkdir(parents=True, exist_ok=True)

    _write_release_metadata(tag_dir, release)

    selected_assets = _select_assets(release, repo_cfg)
    if not selected_assets:
        logging.info("[%s:%s] No assets matched rules; marking as processed.", repo_key, tag)
        existing_state = repo_state.get("releases", {}).get(tag, {}) if isinstance(repo_state.get("releases"), dict) else {}
        mark_release_processed(repo_state, tag, list(existing_state.get("downloaded_assets", []) or []))
        return True

    existing_state = repo_state.get("releases", {}).get(tag, {}) if isinstance(repo_state.get("releases"), dict) else {}
    downloaded_assets = set(existing_state.get("downloaded_assets", []) or [])

    ok = True
    for asset_name in selected_assets:
        dest_file = tag_dir / asset_name
        if dest_file.exists() and dest_file.stat().st_size > 0:
            downloaded_assets.add(asset_name)
            continue

        logging.info("[%s:%s] Downloading asset: %s", repo_key, tag, asset_name)
        try:
            downloader.download_release_asset(repo_https_url, tag, asset_name, tag_dir)
        except DownloadError as exc:
            logging.error("[%s:%s] Download failed for %s: %s", repo_key, tag, asset_name, exc)
            ok = False
            continue

        if dest_file.exists() and dest_file.stat().st_size > 0:
            downloaded_assets.add(asset_name)

    mark_release_processed(repo_state, tag, sorted(downloaded_assets))
    return ok


def _write_release_metadata(tag_dir: Path, release: Release) -> None:
    meta_path = tag_dir / "release.json"
    payload = {
        "tag_name": release.tag_name,
        "draft": release.draft,
        "prerelease": release.prerelease,
        "created_at": release.created_at.isoformat() if release.created_at else None,
        "published_at": release.published_at.isoformat() if release.published_at else None,
        "html_url": release.html_url,
        "assets": [{"name": a.name, "size": a.size, "browser_download_url": a.browser_download_url} for a in release.assets],
    }
    meta_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _cleanup_old_releases(repo_key: str, repo_dir: Path, keep_tags: list[str], repo_state: dict) -> None:
    keep_dir_names = {_sanitize_path_component(t) for t in keep_tags}

    for child in repo_dir.iterdir():
        if not child.is_dir():
            continue
        if child.name in keep_dir_names:
            continue
        if not (child / "release.json").exists():
            continue

        logging.info("[%s] Removing old release directory: %s", repo_key, child)
        shutil.rmtree(child, ignore_errors=True)

    keep_tag_set = set(keep_tags)
    releases_state = repo_state.get("releases", {})
    if isinstance(releases_state, dict):
        for tag in list(releases_state.keys()):
            if tag not in keep_tag_set:
                remove_release_state(repo_state, tag)
