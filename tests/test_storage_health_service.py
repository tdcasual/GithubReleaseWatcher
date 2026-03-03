from __future__ import annotations

import json
import tempfile
from pathlib import Path

from github_release_watcher.config import AppConfig, load_config
from github_release_watcher.storage_health_service import StorageHealthService


def _write_config(base: Path, *, storage_mode: str = "local") -> AppConfig:
    cfg_path = base / "config.toml"
    cfg_path.write_text(
        "\n".join(
            [
                "interval_seconds = 60",
                'download_dir = "./downloads"',
                'state_file = "./state.json"',
                "keep_last = 1",
                "",
                "[storage]",
                f'mode = "{storage_mode}"',
                "",
                "[storage.webdav]",
                'base_url = "https://example.com/dav/"',
                "",
                "[[repos]]",
                'name = "owner/repo"',
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return load_config(cfg_path)


def test_get_storage_health_aggregates_repo_totals() -> None:
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        cfg = _write_config(base, storage_mode="local")
        cfg.state_file.write_text(
            json.dumps(
                {
                    "version": 1,
                    "repos": {
                        "owner/repo": {
                            "stats": {
                                "upload_retry_total": 3,
                                "upload_verify_failed_total": 2,
                                "upload_queue_depth": 1,
                            }
                        },
                        "owner/another": {
                            "stats": {
                                "upload_retry_total": 5,
                                "upload_verify_failed_total": 0,
                                "upload_queue_depth": 4,
                            }
                        },
                    },
                }
            ),
            encoding="utf-8",
        )

        svc = StorageHealthService()
        payload = svc.get_storage_health(config=cfg)
        assert payload["totals"]["upload_retry_total"] == 8
        assert payload["totals"]["upload_verify_failed_total"] == 2
        assert payload["totals"]["upload_queue_depth"] == 5


def test_sync_webdav_cache_local_mode_returns_empty_totals() -> None:
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        cfg = _write_config(base, storage_mode="local")

        svc = StorageHealthService()
        payload = svc.sync_webdav_cache(config=cfg, prune=False)
        assert payload["mode"] == "local"
        assert payload["totals"]["repos_processed"] == 0


def test_sync_webdav_cache_detects_and_prunes_stale_files() -> None:
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        cfg = _write_config(base, storage_mode="webdav")
        cfg.state_file.write_text(
            json.dumps(
                {
                    "version": 1,
                    "repos": {
                        "owner/repo": {
                            "releases": {
                                "v1": {"downloaded_assets": ["ok.bin", "missing.bin"]},
                            }
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

        cache_tag = cfg.download_dir / ".webdav_cache" / "owner" / "repo" / "v1"
        cache_tag.mkdir(parents=True, exist_ok=True)
        (cache_tag / "ok.bin").write_bytes(b"ok")
        stale = cache_tag / "stale.bin"
        stale.write_bytes(b"stale")

        svc = StorageHealthService()
        preview = svc.sync_webdav_cache(config=cfg, prune=False)
        assert preview["totals"]["stale_files"] == 1
        assert preview["totals"]["missing_files"] == 1
        assert stale.exists()

        pruned = svc.sync_webdav_cache(config=cfg, prune=True)
        assert pruned["totals"]["pruned_files"] == 1
        assert not stale.exists()
