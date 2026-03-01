from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from github_release_watcher.webapp import WatcherService


class WebappApiSmokeTests(unittest.TestCase):
    def _write_base_config(self, base: Path, *, storage_mode: str = "local") -> Path:
        cfg_path = base / "config.toml"
        lines = [
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
        cfg_path.write_text("\n".join(lines), encoding="utf-8")
        return cfg_path

    def test_preview_cleanup_returns_old_tags(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            cfg_path = self._write_base_config(base, storage_mode="local")
            state_path = base / "state.json"
            state_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "repos": {
                            "owner/repo": {
                                "releases": {
                                    "v2.0.0": {"processed_at": "2026-01-01T00:00:00+00:00"},
                                    "v1.0.0": {"processed_at": "2025-01-01T00:00:00+00:00"},
                                }
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            app = WatcherService(cfg_path)
            preview = app.preview_cleanup(repo="owner/repo")

            self.assertEqual(preview["repo"], "owner/repo")
            self.assertIn("v1.0.0", preview["delete_tags"])
            self.assertNotIn("v2.0.0", preview["delete_tags"])

    def test_storage_health_aggregates_upload_stats(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            cfg_path = self._write_base_config(base, storage_mode="local")
            state_path = base / "state.json"
            state_path.write_text(
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
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            app = WatcherService(cfg_path)
            health = app.get_storage_health()

            self.assertEqual(health["totals"]["upload_retry_total"], 3)
            self.assertEqual(health["totals"]["upload_verify_failed_total"], 2)
            self.assertEqual(health["totals"]["upload_queue_depth"], 1)

    def test_sync_webdav_cache_reports_stale_and_missing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            cfg_path = self._write_base_config(base, storage_mode="webdav")
            state_path = base / "state.json"
            state_path.write_text(
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

            cache_tag = base / "downloads" / ".webdav_cache" / "owner" / "repo" / "v1"
            cache_tag.mkdir(parents=True, exist_ok=True)
            (cache_tag / "ok.bin").write_bytes(b"ok")
            (cache_tag / "stale.bin").write_bytes(b"stale")

            app = WatcherService(cfg_path)
            result = app.sync_webdav_cache(prune=False)

            self.assertEqual(result["mode"], "webdav")
            self.assertEqual(result["totals"]["stale_files"], 1)
            self.assertEqual(result["totals"]["missing_files"], 1)
            self.assertTrue((cache_tag / "stale.bin").exists())

    def test_sync_webdav_cache_prune_removes_stale_files(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            cfg_path = self._write_base_config(base, storage_mode="webdav")
            state_path = base / "state.json"
            state_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "repos": {
                            "owner/repo": {
                                "releases": {
                                    "v1": {"downloaded_assets": ["ok.bin"]},
                                }
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            cache_tag = base / "downloads" / ".webdav_cache" / "owner" / "repo" / "v1"
            cache_tag.mkdir(parents=True, exist_ok=True)
            (cache_tag / "ok.bin").write_bytes(b"ok")
            stale = cache_tag / "stale.bin"
            stale.write_bytes(b"stale")

            app = WatcherService(cfg_path)
            result = app.sync_webdav_cache(prune=True)

            self.assertEqual(result["totals"]["pruned_files"], 1)
            self.assertFalse(stale.exists())


if __name__ == "__main__":
    unittest.main()
