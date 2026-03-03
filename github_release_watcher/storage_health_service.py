from __future__ import annotations

from typing import Any

from .config import AppConfig
from .state import load_state


def _sanitize_path_component(value: str) -> str:
    raw = str(value or "").strip()
    raw = raw.replace("/", "__").replace("\\", "__")
    raw = raw.replace("..", "__")
    return raw or "__empty__"


class StorageHealthService:
    def get_storage_health(self, *, config: AppConfig) -> dict[str, Any]:
        state = load_state(config.state_file)
        repos_state = state.get("repos", {}) if isinstance(state.get("repos"), dict) else {}
        totals = {
            "upload_retry_total": 0,
            "upload_verify_failed_total": 0,
            "upload_queue_depth": 0,
        }
        repos: list[dict[str, Any]] = []
        for repo_key, repo_state in repos_state.items():
            if not isinstance(repo_key, str):
                continue
            if not isinstance(repo_state, dict):
                repo_state = {}
            stats = repo_state.get("stats", {}) if isinstance(repo_state.get("stats"), dict) else {}
            retry_total = int(stats.get("upload_retry_total", 0) or 0)
            verify_failed_total = int(stats.get("upload_verify_failed_total", 0) or 0)
            queue_depth = int(stats.get("upload_queue_depth", 0) or 0)
            totals["upload_retry_total"] += retry_total
            totals["upload_verify_failed_total"] += verify_failed_total
            totals["upload_queue_depth"] += queue_depth
            repos.append(
                {
                    "repo": repo_key,
                    "upload_retry_total": retry_total,
                    "upload_verify_failed_total": verify_failed_total,
                    "upload_queue_depth": queue_depth,
                }
            )
        return {"mode": str(getattr(config, "storage_mode", "local") or "local"), "totals": totals, "repos": repos}

    def sync_webdav_cache(self, *, config: AppConfig, prune: bool = False) -> dict[str, Any]:
        mode = str(getattr(config, "storage_mode", "local") or "local")
        cache_root = config.download_dir / ".webdav_cache"
        if mode != "webdav":
            return {
                "mode": mode,
                "prune": bool(prune),
                "totals": {
                    "repos_processed": 0,
                    "cache_files_checked": 0,
                    "expected_files": 0,
                    "stale_files": 0,
                    "missing_files": 0,
                    "pruned_files": 0,
                },
                "items": [],
            }

        state = load_state(config.state_file)
        repos_state = state.get("repos", {}) if isinstance(state.get("repos"), dict) else {}

        totals = {
            "repos_processed": 0,
            "cache_files_checked": 0,
            "expected_files": 0,
            "stale_files": 0,
            "missing_files": 0,
            "pruned_files": 0,
        }
        items: list[dict[str, Any]] = []

        for repo_key, repo_state in repos_state.items():
            if not isinstance(repo_key, str) or "/" not in repo_key:
                continue
            if not isinstance(repo_state, dict):
                repo_state = {}
            owner, repo = repo_key.split("/", 1)
            cache_repo_dir = cache_root / owner / repo
            releases = repo_state.get("releases", {}) if isinstance(repo_state.get("releases"), dict) else {}
            expected: set[str] = set()
            for tag, entry in releases.items():
                if not isinstance(tag, str) or not tag:
                    continue
                entry_dict = entry if isinstance(entry, dict) else {}
                assets = entry_dict.get("downloaded_assets", [])
                tag_dir = _sanitize_path_component(tag)
                if isinstance(assets, list):
                    for asset in assets:
                        if not isinstance(asset, str) or not asset:
                            continue
                        expected.add(f"{tag_dir}/{asset}")

            existing: set[str] = set()
            if cache_repo_dir.exists():
                for p in cache_repo_dir.rglob("*"):
                    if p.is_file():
                        try:
                            existing.add(str(p.relative_to(cache_repo_dir)).replace("\\", "/"))
                        except Exception:
                            continue

            stale = sorted(existing - expected)
            missing = sorted(expected - existing)
            pruned = 0
            if prune:
                for rel in stale:
                    p = cache_repo_dir / rel
                    try:
                        p.unlink()
                        pruned += 1
                    except FileNotFoundError:
                        continue
                    except Exception:
                        continue

            totals["repos_processed"] += 1
            totals["cache_files_checked"] += len(existing)
            totals["expected_files"] += len(expected)
            totals["stale_files"] += len(stale)
            totals["missing_files"] += len(missing)
            totals["pruned_files"] += pruned
            items.append(
                {
                    "repo": repo_key,
                    "cache_files_checked": len(existing),
                    "expected_files": len(expected),
                    "stale_files": len(stale),
                    "missing_files": len(missing),
                    "pruned_files": pruned,
                    "stale_examples": stale[:10],
                    "missing_examples": missing[:10],
                }
            )

        return {"mode": mode, "prune": bool(prune), "totals": totals, "items": items}
