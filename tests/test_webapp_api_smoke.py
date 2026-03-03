from __future__ import annotations

import http.client
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from github_release_watcher.webapp import AuthService, Handler, WatcherService, _Server


class WebappApiSmokeTests(unittest.TestCase):
    def _write_base_config(self, base: Path, *, storage_mode: str = "local", repos: list[str] | None = None) -> Path:
        cfg_path = base / "config.toml"
        repo_list = repos if isinstance(repos, list) and repos else ["owner/repo"]
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
        ]
        for spec in repo_list:
            lines.extend(["[[repos]]", f'name = "{spec}"', ""])
        cfg_path.write_text("\n".join(lines), encoding="utf-8")
        return cfg_path

    def _start_server_with_session(self, app: WatcherService) -> tuple[_Server, threading.Thread, str]:
        auth = AuthService(app)
        token = auth.create_session(app.auth_username())
        server = _Server(("127.0.0.1", 0), Handler, app=app, ui=False, auth=auth)
        t = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True)
        t.start()
        time.sleep(0.02)
        return server, t, token

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

    def test_enqueue_run_once_supports_batch_repos(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            cfg_path = self._write_base_config(base, repos=["owner/repo", "owner/another"])
            app = WatcherService(cfg_path)

            queued = app.enqueue_run_once(source="api", repos=["owner/repo", "owner/another"])

            self.assertTrue(queued)
            task = app._queue.get_nowait()  # type: ignore[attr-defined]
            self.assertEqual(task.get("type"), "run_once")
            self.assertEqual(task.get("repo_keys"), ["owner/repo", "owner/another"])

    def test_enqueue_run_once_batch_repos_unknown_repo_raises(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            cfg_path = self._write_base_config(base, repos=["owner/repo"])
            app = WatcherService(cfg_path)

            with self.assertRaises(ValueError):
                app.enqueue_run_once(source="api", repos=["owner/repo", "owner/missing"])

    def test_run_api_rejects_null_repos_field(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            cfg_path = self._write_base_config(base, repos=["owner/repo"])
            app = WatcherService(cfg_path)
            app.set_credentials("tester", "pass")
            server, thread, token = self._start_server_with_session(app)
            conn: http.client.HTTPConnection | None = None
            try:
                host, port = server.server_address
                conn = http.client.HTTPConnection(str(host), int(port), timeout=3)
                conn.request(
                    "POST",
                    "/api/v1/run",
                    body=json.dumps({"repos": None}),
                    headers={
                        "Content-Type": "application/json",
                        "Cookie": f"grw_session={token}",
                    },
                )
                res = conn.getresponse()
                body = res.read().decode("utf-8")
                payload = json.loads(body)
                self.assertEqual(res.status, 400)
                self.assertEqual(payload.get("error"), "repos must be a list")
            finally:
                if conn is not None:
                    conn.close()
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
                app.shutdown()

    def test_run_api_returns_queue_status(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            cfg_path = self._write_base_config(base, repos=["owner/repo"])
            app = WatcherService(cfg_path)
            app.set_credentials("tester", "pass")
            server, thread, token = self._start_server_with_session(app)
            conn: http.client.HTTPConnection | None = None
            try:
                host, port = server.server_address
                conn = http.client.HTTPConnection(str(host), int(port), timeout=3)
                headers = {
                    "Content-Type": "application/json",
                    "Cookie": f"grw_session={token}",
                }

                conn.request("POST", "/api/v1/run", body=json.dumps({"repo": "owner/repo"}), headers=headers)
                first_res = conn.getresponse()
                first_payload = json.loads(first_res.read().decode("utf-8"))

                conn.request("POST", "/api/v1/run", body=json.dumps({"repo": "owner/repo"}), headers=headers)
                second_res = conn.getresponse()
                second_payload = json.loads(second_res.read().decode("utf-8"))

                self.assertEqual(first_res.status, 200)
                self.assertEqual(first_payload.get("queue_status"), "accepted")
                self.assertTrue(first_payload.get("queued"))
                self.assertIn("status", first_payload)

                self.assertEqual(second_res.status, 200)
                self.assertEqual(second_payload.get("queue_status"), "deduplicated")
                self.assertFalse(second_payload.get("queued"))
                self.assertIn("status", second_payload)
            finally:
                if conn is not None:
                    conn.close()
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
                app.shutdown()


if __name__ == "__main__":
    unittest.main()
