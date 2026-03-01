from __future__ import annotations

import json
import logging
import re
import shutil
import statistics
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import nullcontext, suppress
from datetime import datetime, timezone
import time
from pathlib import Path
from typing import Iterable

import requests

from .config import AppConfig, RepoConfig
from .downloader import DownloadError, GitHubReleaseAssetDownloader
from .github import Asset, GitHubApiError, GitHubClient, Release, parse_repo_spec
from .state import append_repo_activity, get_repo_state, load_state, mark_release_processed, remove_release_state, save_state
from .webdav import WebDAVClient, WebDAVError

activity_logger = logging.getLogger("github_release_watcher.activity")


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _repo_stats(repo_state: dict) -> dict:
    stats = repo_state.setdefault("stats", {})
    if not isinstance(stats, dict):
        stats = {}
        repo_state["stats"] = stats
    return stats


def _inc_stat(stats: dict, key: str, amount: int = 1) -> None:
    try:
        stats[key] = int(stats.get(key, 0) or 0) + int(amount)
    except Exception:
        stats[key] = int(amount)


def _mark_last_error(stats: dict, *, error_type: str, error: str) -> None:
    stats["last_check_had_errors"] = True
    stats["last_error_type"] = error_type
    stats["last_error"] = error
    if error_type == "network":
        stats["last_check_had_network_error"] = True


def _is_network_error(exc: Exception) -> bool:
    if isinstance(exc, requests.RequestException):
        return True
    msg = str(exc).lower()
    if isinstance(exc, GitHubApiError):
        if "request failed after retries" in msg:
            return True
        if "429" in msg or "502" in msg or "503" in msg or "504" in msg:
            return True
        return False
    if isinstance(exc, WebDAVError):
        return True
    if isinstance(exc, DownloadError):
        if "transient http" in msg:
            return True
        if "timeout" in msg or "timed out" in msg:
            return True
        if "connection" in msg or "reset" in msg:
            return True
        if "download failed after" in msg:
            return True
    return False


def _record_repo_event(repo_state: dict, *, event_type: str, message: str, tag: str | None = None, **extra) -> None:
    payload = {"type": event_type, "message": message}
    if tag:
        payload["tag"] = tag
    payload.update({k: v for k, v in extra.items() if v is not None})
    append_repo_activity(repo_state, payload)


def _compute_update_stats(releases: list[Release]) -> dict:
    times: list[datetime] = []
    for r in releases:
        t = r.published_at or r.created_at
        if t is not None:
            times.append(t)
    times.sort(reverse=True)

    intervals: list[float] = []
    for a, b in zip(times, times[1:]):
        delta = (a - b).total_seconds()
        if delta > 0:
            intervals.append(delta)

    if len(intervals) < 2:
        return {"sample_count": len(intervals), "median_interval_seconds": None, "mean_interval_seconds": None}

    median = float(statistics.median(intervals))
    mean = float(sum(intervals) / len(intervals))
    return {
        "sample_count": len(intervals),
        "median_interval_seconds": int(median),
        "mean_interval_seconds": int(mean),
    }


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
    downloader = GitHubReleaseAssetDownloader(github_token=config.github.token)

    storage_mode = str(getattr(config, "storage_mode", "local") or "local").strip().lower()
    webdav: WebDAVClient | None = None
    if storage_mode == "webdav":
        try:
            webdav = WebDAVClient(config.webdav)
        except Exception as exc:
            logging.error("Invalid WebDAV config: %s", exc)
            return 1

    had_errors = False
    for repo_cfg in config.repos:
        if not getattr(repo_cfg, "enabled", True):
            logging.info("Skipping disabled repo: %s", repo_cfg.name)
            continue

        try:
            owner, repo, _ = parse_repo_spec(repo_cfg.name)
            repo_key = f"{owner}/{repo}"
        except Exception as exc:
            logging.exception("Invalid repo config: %s", repo_cfg.name)
            had_errors = True
            continue

        repo_state = get_repo_state(state, repo_key)
        stats = _repo_stats(repo_state)
        _inc_stat(stats, "checks_total", 1)
        stats["last_check_started_at"] = _utc_now_iso()
        stats["last_check_finished_at"] = None
        stats["last_check_ok"] = None
        stats["last_check_had_errors"] = False
        stats["last_check_had_network_error"] = False
        stats["last_error_type"] = None
        stats["last_error"] = None
        _record_repo_event(repo_state, event_type="check_start", message=f"{repo_key} 开始检查")

        try:
            ok = _process_repo(config, repo_cfg, github, downloader, state, webdav=webdav)
            had_errors = had_errors or not ok
        except Exception as exc:
            logging.exception("Failed processing repo %s", repo_cfg.name)
            ok = False
            err = str(exc)
            error_type = "network" if _is_network_error(exc) else "other"
            _mark_last_error(stats, error_type=error_type, error=err)
            _inc_stat(stats, "checks_failed", 1)
            if error_type == "network":
                _inc_stat(stats, "checks_network_failed", 1)
            _record_repo_event(repo_state, event_type="check_error", message=err, tag=None, error_type=error_type)
            had_errors = True
        else:
            if ok:
                _inc_stat(stats, "checks_ok", 1)
                _record_repo_event(repo_state, event_type="check_ok", message="检查成功")
            else:
                _inc_stat(stats, "checks_failed", 1)
                if stats.get("last_check_had_network_error") or stats.get("last_error_type") == "network":
                    _inc_stat(stats, "checks_network_failed", 1)
                if not stats.get("last_error"):
                    _mark_last_error(stats, error_type="other", error="check had errors")
                _record_repo_event(
                    repo_state,
                    event_type="check_error",
                    message=str(stats.get("last_error") or "检查有错误"),
                    error_type=str(stats.get("last_error_type") or "other"),
                )
        finally:
            stats["last_check_finished_at"] = _utc_now_iso()
            stats["last_check_ok"] = bool(ok)

    try:
        save_state(config.state_file, state)
    except Exception:
        logging.exception("Failed saving state file: %s", config.state_file)
        return 1
    return 1 if had_errors else 0


def _process_repo(
    config: AppConfig,
    repo_cfg: RepoConfig,
    github: GitHubClient,
    downloader: GitHubReleaseAssetDownloader,
    state: dict,
    *,
    webdav: WebDAVClient | None,
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

    repo_state = get_repo_state(state, repo_key)
    stats = _repo_stats(repo_state)

    stats["keep_last_effective"] = int(keep_last)
    latest = wanted[0] if wanted else None
    if latest is not None:
        stats["latest_release_tag"] = latest.tag_name
        stats["latest_release_published_at"] = latest.published_at.isoformat() if latest.published_at else None
        stats["current_tag"] = latest.tag_name
        stats["current_published_at"] = latest.published_at.isoformat() if latest.published_at else None

        releases_state = repo_state.get("releases", {})
        known_tags = set(releases_state.keys()) if isinstance(releases_state, dict) else set()
        if latest.tag_name and latest.tag_name not in known_tags:
            _inc_stat(stats, "new_releases_detected", 1)
            _record_repo_event(repo_state, event_type="new_release", message=f"发现新版本：{latest.tag_name}", tag=latest.tag_name)

    update = repo_state.setdefault("update", {})
    if not isinstance(update, dict):
        update = {}
        repo_state["update"] = update
    update_stats = _compute_update_stats(releases)
    update.update(update_stats)
    update["computed_at"] = _utc_now_iso()

    ok = True
    if webdav is None:
        repo_dir = config.download_dir / owner / repo
        repo_dir.mkdir(parents=True, exist_ok=True)

        for release in reversed(wanted):
            ok = (
                _ensure_release_downloaded_local(
                    repo_key, repo_https_url, repo_dir, repo_cfg, release, downloader, repo_state
                )
                and ok
            )

        _cleanup_old_releases_local(repo_key, repo_dir, wanted_tags, repo_state)
        stats = _repo_stats(repo_state)
        stats["storage_mode"] = "local"
        stats["download_root"] = str(repo_dir)
        current_tag = stats.get("current_tag")
        releases_state = repo_state.get("releases", {})
        if isinstance(current_tag, str) and isinstance(releases_state, dict):
            current_entry = releases_state.get(current_tag, {}) if isinstance(releases_state.get(current_tag), dict) else {}
            stats["current_processed_at"] = current_entry.get("processed_at")
        return ok

    cache_root = config.download_dir / ".webdav_cache"
    cache_repo_dir = cache_root / owner / repo
    cache_repo_dir.mkdir(parents=True, exist_ok=True)
    with suppress(Exception):
        stats["webdav_capabilities"] = webdav.detect_capabilities()

    webdav_release_kwargs = {
        "max_retries": int(getattr(config.webdav, "max_retries", 3) or 3),
        "retry_backoff_seconds": int(getattr(config.webdav, "retry_backoff_seconds", 2) or 2),
        "verify_after_upload": bool(getattr(config.webdav, "verify_after_upload", True)),
        "upload_temp_suffix": str(getattr(config.webdav, "upload_temp_suffix", ".uploading") or ".uploading"),
    }
    upload_concurrency = int(getattr(config.webdav, "upload_concurrency", 1) or 1)
    releases_to_process = list(reversed(wanted))
    if upload_concurrency <= 1 or len(releases_to_process) <= 1:
        for release in releases_to_process:
            ok = (
                _ensure_release_downloaded_webdav(
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
                    state_lock=None,
                    **webdav_release_kwargs,
                )
                and ok
            )
    else:
        workers = min(upload_concurrency, len(releases_to_process))
        state_lock = threading.Lock()
        logging.info("[%s] WebDAV release upload with %d workers.", repo_key, workers)
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_release = {
                executor.submit(
                    _ensure_release_downloaded_webdav,
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
                    state_lock=state_lock,
                    **webdav_release_kwargs,
                ): release
                for release in releases_to_process
            }
            for future in as_completed(future_to_release):
                release = future_to_release[future]
                tag = release.tag_name
                try:
                    release_ok = future.result()
                except Exception as exc:
                    logging.exception("[%s:%s] WebDAV release sync crashed: %s", repo_key, tag, exc)
                    with state_lock:
                        stats = _repo_stats(repo_state)
                        error_type = "network" if _is_network_error(exc) else "other"
                        _mark_last_error(stats, error_type=error_type, error=f"{tag}: {exc}")
                        _record_repo_event(
                            repo_state,
                            event_type="download_error",
                            message=f"{tag} 同步失败：{exc}",
                            tag=tag,
                            error_type=error_type,
                            path=f"webdav:{owner}/{repo}/{_sanitize_path_component(tag)}",
                        )
                    ok = False
                    continue
                ok = release_ok and ok

    _cleanup_old_releases_webdav(
        repo_key,
        owner,
        repo,
        webdav,
        wanted_tags,
        repo_state,
        cleanup_mode=str(getattr(config.webdav, "cleanup_mode", "delete") or "delete"),
    )
    stats = _repo_stats(repo_state)
    stats["storage_mode"] = "webdav"
    stats["download_root"] = f"webdav:{owner}/{repo}"
    current_tag = stats.get("current_tag")
    releases_state = repo_state.get("releases", {})
    if isinstance(current_tag, str) and isinstance(releases_state, dict):
        current_entry = releases_state.get(current_tag, {}) if isinstance(releases_state.get(current_tag), dict) else {}
        stats["current_processed_at"] = current_entry.get("processed_at")
    return ok

def _release_metadata_bytes(release: Release) -> bytes:
    payload = {
        "tag_name": release.tag_name,
        "draft": release.draft,
        "prerelease": release.prerelease,
        "created_at": release.created_at.isoformat() if release.created_at else None,
        "published_at": release.published_at.isoformat() if release.published_at else None,
        "html_url": release.html_url,
        "assets": [{"name": a.name, "size": a.size, "browser_download_url": a.browser_download_url} for a in release.assets],
    }
    return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


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


def _select_assets(release: Release, repo_cfg: RepoConfig) -> list[Asset]:
    include = _compile_patterns(repo_cfg.include_assets)
    exclude = _compile_patterns(repo_cfg.exclude_assets)
    asset_types = [t.strip().lower().lstrip(".") for t in getattr(repo_cfg, "asset_types", []) if t and t.strip()]

    selected: list[Asset] = []
    for asset in release.assets:
        name = asset.name
        if not _is_safe_filename(name):
            continue

        if asset_types:
            lower_name = name.lower()
            if not any(lower_name.endswith("." + t) for t in asset_types):
                continue

        if include and not any(p.search(name) for p in include):
            continue
        if exclude and any(p.search(name) for p in exclude):
            continue
        selected.append(asset)
    return selected


def _is_asset_valid(asset: Asset, dest_file: Path) -> bool:
    if not dest_file.exists():
        return False
    try:
        size = int(dest_file.stat().st_size)
    except Exception:
        return False
    if asset.size is None:
        return size > 0
    if asset.size <= 0:
        return size > 0
    return size == int(asset.size)


def _ensure_release_downloaded_local(
    repo_key: str,
    repo_https_url: str,
    repo_dir: Path,
    repo_cfg: RepoConfig,
    release: Release,
    downloader: GitHubReleaseAssetDownloader,
    repo_state: dict,
) -> bool:
    tag = release.tag_name
    tag_dir = repo_dir / _sanitize_path_component(tag)
    tag_dir.mkdir(parents=True, exist_ok=True)

    _write_release_metadata_local(tag_dir, release)

    selected_assets = _select_assets(release, repo_cfg)
    if not selected_assets:
        logging.info("[%s:%s] No assets matched rules; marking as processed.", repo_key, tag)
        existing_state = repo_state.get("releases", {}).get(tag, {}) if isinstance(repo_state.get("releases"), dict) else {}
        mark_release_processed(
            repo_state,
            tag,
            list(existing_state.get("downloaded_assets", []) or []),
            published_at=release.published_at.isoformat() if release.published_at else None,
            created_at=release.created_at.isoformat() if release.created_at else None,
            html_url=release.html_url,
        )
        return True

    existing_state = repo_state.get("releases", {}).get(tag, {}) if isinstance(repo_state.get("releases"), dict) else {}
    downloaded_assets = set(existing_state.get("downloaded_assets", []) or [])

    ok = True
    for asset in selected_assets:
        dest_file = tag_dir / asset.name
        if _is_asset_valid(asset, dest_file):
            downloaded_assets.add(asset.name)
            continue
        if dest_file.exists():
            logging.warning(
                "[%s:%s] Existing file size mismatch; re-downloading: %s",
                repo_key,
                tag,
                asset.name,
            )

        logging.info("[%s:%s] Downloading asset: %s", repo_key, tag, asset.name)
        try:
            downloader.download_release_asset(repo_https_url, tag, asset, tag_dir)
        except DownloadError as exc:
            logging.error("[%s:%s] Download failed for %s: %s", repo_key, tag, asset.name, exc)
            stats = _repo_stats(repo_state)
            _inc_stat(stats, "download_errors_total", 1)
            error_type = "network" if _is_network_error(exc) else "other"
            _mark_last_error(stats, error_type=error_type, error=f"{asset.name}: {exc}")
            activity_logger.warning(
                "%s %s 下载失败：%s",
                repo_key,
                tag,
                asset.name,
                extra={
                    "event_type": "download_error",
                    "repo": repo_key,
                    "tag": tag,
                    "path": str(tag_dir),
                },
            )
            _record_repo_event(
                repo_state,
                event_type="download_error",
                message=f"{asset.name} 下载失败：{exc}",
                tag=tag,
                asset=asset.name,
                error_type=error_type,
                path=str(tag_dir),
            )
            ok = False
            continue

        if _is_asset_valid(asset, dest_file):
            downloaded_assets.add(asset.name)
            stats = _repo_stats(repo_state)
            _inc_stat(stats, "download_assets_total", 1)
            activity_logger.info(
                "%s %s 下载：%s → %s",
                repo_key,
                tag,
                asset.name,
                str(tag_dir),
                extra={
                    "event_type": "download",
                    "repo": repo_key,
                    "tag": tag,
                    "path": str(tag_dir),
                },
            )
            _record_repo_event(
                repo_state,
                event_type="download",
                message=f"下载：{asset.name}",
                tag=tag,
                asset=asset.name,
                path=str(tag_dir),
            )

    mark_release_processed(
        repo_state,
        tag,
        sorted(downloaded_assets),
        published_at=release.published_at.isoformat() if release.published_at else None,
        created_at=release.created_at.isoformat() if release.created_at else None,
        html_url=release.html_url,
    )
    return ok


def _write_release_metadata_local(tag_dir: Path, release: Release) -> None:
    meta_path = tag_dir / "release.json"
    meta_path.write_bytes(_release_metadata_bytes(release))


def _upload_file_to_webdav(
    webdav: WebDAVClient,
    *,
    remote_path: str,
    local_path: Path,
    expected_size: int | None,
    repo_state: dict,
    state_lock=None,
    max_retries: int,
    retry_backoff_seconds: int,
    verify_after_upload: bool,
    upload_temp_suffix: str,
) -> None:
    def _inc_upload_stat(key: str, amount: int = 1) -> None:
        with (state_lock if state_lock is not None else nullcontext()):
            stats = _repo_stats(repo_state)
            _inc_stat(stats, key, amount)

    max_retries = max(1, int(max_retries))
    backoff = max(1, int(retry_backoff_seconds))
    suffix = str(upload_temp_suffix or ".uploading")
    if "/" in suffix or "\\" in suffix:
        suffix = ".uploading"

    last_error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        temp_remote = f"{remote_path}{suffix}"
        try:
            with suppress(Exception):
                webdav.delete(temp_remote, is_dir=False)
            webdav.put_file(temp_remote, local_path, content_type="application/octet-stream")
            try:
                webdav.move(temp_remote, remote_path, overwrite=True)
            except WebDAVError:
                # Some servers disable MOVE for files; fallback to direct PUT.
                webdav.put_file(remote_path, local_path, content_type="application/octet-stream")
                with suppress(Exception):
                    webdav.delete(temp_remote, is_dir=False)

            if verify_after_upload:
                exists, remote_size = webdav.stat_file(remote_path)
                if not exists:
                    _inc_upload_stat("upload_verify_failed_total", 1)
                    raise WebDAVError("remote file not found after upload")
                if expected_size is not None and remote_size is not None and int(remote_size) != int(expected_size):
                    _inc_upload_stat("upload_verify_failed_total", 1)
                    raise WebDAVError(f"remote size mismatch: expected {expected_size}, got {remote_size}")
            return
        except Exception as exc:
            last_error = exc
            with suppress(Exception):
                webdav.delete(temp_remote, is_dir=False)
            if attempt >= max_retries:
                break
            _inc_upload_stat("upload_retry_total", 1)
            time.sleep(min(backoff * (2 ** (attempt - 1)), 30))

    raise WebDAVError(f"webdav upload failed after {max_retries} attempts: {last_error}")


def _ensure_release_downloaded_webdav(
    repo_key: str,
    owner: str,
    repo: str,
    repo_https_url: str,
    cache_repo_dir: Path,
    repo_cfg: RepoConfig,
    release: Release,
    downloader: GitHubReleaseAssetDownloader,
    webdav: WebDAVClient,
    repo_state: dict,
    state_lock=None,
    *,
    max_retries: int,
    retry_backoff_seconds: int,
    verify_after_upload: bool,
    upload_temp_suffix: str,
) -> bool:
    def _state_guard():
        return state_lock if state_lock is not None else nullcontext()

    tag = release.tag_name
    tag_dir_name = _sanitize_path_component(tag)
    remote_tag_dir = f"{owner}/{repo}/{tag_dir_name}"

    try:
        webdav.ensure_dir(remote_tag_dir)
        webdav.put_bytes(f"{remote_tag_dir}/release.json", _release_metadata_bytes(release), content_type="application/json")
    except WebDAVError as exc:
        logging.error("[%s:%s] WebDAV metadata upload failed: %s", repo_key, tag, exc)
        activity_logger.warning(
            "%s %s 上传元数据失败",
            repo_key,
            tag,
            extra={"event_type": "download_error", "repo": repo_key, "tag": tag, "path": remote_tag_dir},
        )
        return False

    selected_assets = _select_assets(release, repo_cfg)
    if not selected_assets:
        logging.info("[%s:%s] No assets matched rules; marking as processed.", repo_key, tag)
        with _state_guard():
            existing_state = (
                repo_state.get("releases", {}).get(tag, {}) if isinstance(repo_state.get("releases"), dict) else {}
            )
            mark_release_processed(
                repo_state,
                tag,
                list(existing_state.get("downloaded_assets", []) or []),
                published_at=release.published_at.isoformat() if release.published_at else None,
                created_at=release.created_at.isoformat() if release.created_at else None,
                html_url=release.html_url,
            )
        return True

    with _state_guard():
        existing_state = repo_state.get("releases", {}).get(tag, {}) if isinstance(repo_state.get("releases"), dict) else {}
    downloaded_assets = set(existing_state.get("downloaded_assets", []) or [])

    ok = True
    cache_tag_dir = cache_repo_dir / tag_dir_name
    cache_tag_dir.mkdir(parents=True, exist_ok=True)
    with _state_guard():
        stats = _repo_stats(repo_state)
        stats["upload_queue_depth"] = len(selected_assets)

    for idx, asset in enumerate(selected_assets, start=1):
        remote_path = f"{remote_tag_dir}/{asset.name}"
        try:
            exists, remote_size = webdav.stat_file(remote_path)
            if exists and asset.size is not None and remote_size is not None and int(remote_size) == int(asset.size):
                downloaded_assets.add(asset.name)
                with _state_guard():
                    stats = _repo_stats(repo_state)
                    stats["upload_queue_depth"] = max(0, len(selected_assets) - idx)
                continue
        except WebDAVError:
            # If we cannot stat, fall back to upload.
            pass

        logging.info("[%s:%s] Downloading asset for WebDAV: %s", repo_key, tag, asset.name)
        try:
            result = downloader.download_release_asset(repo_https_url, tag, asset, cache_tag_dir)
        except DownloadError as exc:
            logging.error("[%s:%s] Download failed for %s: %s", repo_key, tag, asset.name, exc)
            error_type = "network" if _is_network_error(exc) else "other"
            with _state_guard():
                stats = _repo_stats(repo_state)
                _inc_stat(stats, "download_errors_total", 1)
                _mark_last_error(stats, error_type=error_type, error=f"{asset.name}: {exc}")
            activity_logger.warning(
                "%s %s 下载失败：%s",
                repo_key,
                tag,
                asset.name,
                extra={"event_type": "download_error", "repo": repo_key, "tag": tag, "path": remote_tag_dir},
            )
            with _state_guard():
                _record_repo_event(
                    repo_state,
                    event_type="download_error",
                    message=f"{asset.name} 下载失败：{exc}",
                    tag=tag,
                    asset=asset.name,
                    error_type=error_type,
                    path=f"webdav:{remote_tag_dir}",
                )
            ok = False
            continue

        try:
            _upload_file_to_webdav(
                webdav,
                remote_path=remote_path,
                local_path=result.path,
                expected_size=asset.size,
                repo_state=repo_state,
                state_lock=state_lock,
                max_retries=max_retries,
                retry_backoff_seconds=retry_backoff_seconds,
                verify_after_upload=verify_after_upload,
                upload_temp_suffix=upload_temp_suffix,
            )
        except WebDAVError as exc:
            logging.error("[%s:%s] WebDAV upload failed for %s: %s", repo_key, tag, asset.name, exc)
            activity_logger.warning(
                "%s %s 上传失败：%s",
                repo_key,
                tag,
                asset.name,
                extra={"event_type": "download_error", "repo": repo_key, "tag": tag, "path": remote_tag_dir},
            )
            error_type = "network" if _is_network_error(exc) else "other"
            with _state_guard():
                stats = _repo_stats(repo_state)
                _inc_stat(stats, "download_errors_total", 1)
                _mark_last_error(stats, error_type=error_type, error=f"{asset.name}: {exc}")
                _record_repo_event(
                    repo_state,
                    event_type="download_error",
                    message=f"{asset.name} 上传失败：{exc}",
                    tag=tag,
                    asset=asset.name,
                    error_type=error_type,
                    path=f"webdav:{remote_tag_dir}",
                )
            ok = False
            continue
        finally:
            with suppress(FileNotFoundError):
                result.path.unlink()

        downloaded_assets.add(asset.name)
        with _state_guard():
            stats = _repo_stats(repo_state)
            _inc_stat(stats, "download_assets_total", 1)
            stats["upload_queue_depth"] = max(0, len(selected_assets) - idx)
        activity_logger.info(
            "%s %s 下载：%s → %s",
            repo_key,
            tag,
            asset.name,
            f"webdav:{remote_tag_dir}",
            extra={"event_type": "download", "repo": repo_key, "tag": tag, "path": f"webdav:{remote_tag_dir}"},
        )
        with _state_guard():
            _record_repo_event(
                repo_state,
                event_type="download",
                message=f"下载：{asset.name}",
                tag=tag,
                asset=asset.name,
                path=f"webdav:{remote_tag_dir}",
            )

    with _state_guard():
        mark_release_processed(
            repo_state,
            tag,
            sorted(downloaded_assets),
            published_at=release.published_at.isoformat() if release.published_at else None,
            created_at=release.created_at.isoformat() if release.created_at else None,
            html_url=release.html_url,
        )
    with suppress(Exception):
        if cache_tag_dir.exists() and not any(cache_tag_dir.iterdir()):
            cache_tag_dir.rmdir()
    with _state_guard():
        stats = _repo_stats(repo_state)
        stats["upload_queue_depth"] = 0
    return ok


def _cleanup_old_releases_local(repo_key: str, repo_dir: Path, keep_tags: list[str], repo_state: dict) -> None:
    keep_dir_names = {_sanitize_path_component(t) for t in keep_tags}

    for child in repo_dir.iterdir():
        if not child.is_dir():
            continue
        if child.name in keep_dir_names:
            continue
        meta_path = child / "release.json"
        if not meta_path.exists():
            continue

        deleted_tag = child.name
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if isinstance(meta, dict) and meta.get("tag_name"):
                deleted_tag = str(meta.get("tag_name") or deleted_tag)
        except Exception:
            deleted_tag = child.name

        logging.info("[%s] Removing old release directory: %s", repo_key, child)
        shutil.rmtree(child, ignore_errors=True)
        stats = _repo_stats(repo_state)
        _inc_stat(stats, "cleanup_tags_total", 1)
        activity_logger.info(
            "%s 删除旧版本：%s → %s",
            repo_key,
            child.name,
            str(child),
            extra={
                "event_type": "cleanup",
                "repo": repo_key,
                "tag": child.name,
                "path": str(child),
            },
        )
        _record_repo_event(
            repo_state,
            event_type="cleanup",
            message=f"删除旧版本：{deleted_tag}",
            tag=deleted_tag,
            path=str(child),
        )

    keep_tag_set = set(keep_tags)
    releases_state = repo_state.get("releases", {})
    if isinstance(releases_state, dict):
        for tag in list(releases_state.keys()):
            if tag not in keep_tag_set:
                remove_release_state(repo_state, tag)


def _cleanup_old_releases_webdav(
    repo_key: str,
    owner: str,
    repo: str,
    webdav: WebDAVClient,
    keep_tags: list[str],
    repo_state: dict,
    *,
    cleanup_mode: str,
) -> None:
    keep_tag_set = set(keep_tags)
    releases_state = repo_state.get("releases", {})
    if not isinstance(releases_state, dict):
        return

    for tag in list(releases_state.keys()):
        if tag in keep_tag_set:
            continue

        tag_dir_name = _sanitize_path_component(tag)
        remote_tag_dir = f"{owner}/{repo}/{tag_dir_name}"
        entry = releases_state.get(tag, {}) if isinstance(releases_state.get(tag), dict) else {}
        downloaded = entry.get("downloaded_assets", []) if isinstance(entry.get("downloaded_assets"), list) else []

        ok = True
        mode = str(cleanup_mode or "delete").strip().lower()
        if mode == "trash":
            trash_dir = f".trash/{owner}/{repo}"
            trash_target = f"{trash_dir}/{int(time.time())}-{tag_dir_name}"
            try:
                webdav.ensure_dir(trash_dir)
                webdav.move(remote_tag_dir, trash_target, overwrite=False)
            except WebDAVError:
                ok = False

        if not ok or mode != "trash":
            ok = True
            for name in downloaded:
                try:
                    webdav.delete(f"{remote_tag_dir}/{name}", is_dir=False)
                except WebDAVError:
                    ok = False

            try:
                webdav.delete(f"{remote_tag_dir}/release.json", is_dir=False)
            except WebDAVError:
                ok = False

            try:
                webdav.delete(remote_tag_dir, is_dir=True)
            except WebDAVError:
                ok = False

        if ok:
            stats = _repo_stats(repo_state)
            _inc_stat(stats, "cleanup_tags_total", 1)
            activity_logger.info(
                "%s 删除旧版本：%s → %s",
                repo_key,
                tag,
                f"webdav:{remote_tag_dir}",
                extra={"event_type": "cleanup", "repo": repo_key, "tag": tag, "path": f"webdav:{remote_tag_dir}"},
            )
            _record_repo_event(
                repo_state,
                event_type="cleanup",
                message=f"删除旧版本：{tag}",
                tag=tag,
                path=f"webdav:{remote_tag_dir}",
            )
            remove_release_state(repo_state, tag)
        else:
            stats = _repo_stats(repo_state)
            _inc_stat(stats, "cleanup_errors_total", 1)
            _mark_last_error(stats, error_type="network", error=f"cleanup failed: {tag}")
            _record_repo_event(
                repo_state,
                event_type="cleanup_error",
                message=f"删除旧版本失败：{tag}",
                tag=tag,
                error_type="network",
                path=f"webdav:{remote_tag_dir}",
            )
