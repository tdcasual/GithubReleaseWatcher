from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from github_release_watcher.config import WebDAVConfig, load_config
from github_release_watcher.webdav import WebDAVClient


class _FakeResponse:
    def __init__(self, status_code: int, *, headers: dict[str, str] | None = None, text: str = ""):
        self.status_code = status_code
        self.headers = headers or {}
        self.text = text

    def close(self) -> None:
        return


class _FakeSession:
    def __init__(self):
        self.calls: list[tuple[str, str]] = []

    def request(self, method: str, url: str, **kwargs):
        self.calls.append((method, url))
        if method == "OPTIONS":
            return _FakeResponse(
                200,
                headers={
                    "Allow": "OPTIONS, PROPFIND, MKCOL, PUT, DELETE, HEAD, MOVE",
                    "DAV": "1,2",
                },
            )
        if method == "HEAD":
            return _FakeResponse(200, headers={"Content-Length": "0"})
        return _FakeResponse(200)


class WebDAVReliabilityTests(unittest.TestCase):
    def test_detect_capabilities_from_options_and_head(self) -> None:
        client = WebDAVClient(WebDAVConfig(base_url="https://example.com/dav/"))
        client._session = _FakeSession()  # type: ignore[attr-defined]

        caps = client.detect_capabilities()

        self.assertTrue(caps.get("propfind"))
        self.assertTrue(caps.get("mkcol"))
        self.assertTrue(caps.get("put"))
        self.assertTrue(caps.get("delete"))
        self.assertTrue(caps.get("head"))
        self.assertTrue(caps.get("move"))

    def test_load_config_parses_webdav_reliability_fields(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cfg_path = Path(td) / "config.toml"
            cfg_path.write_text(
                "\n".join(
                    [
                        "interval_seconds = 60",
                        'download_dir = "./downloads"',
                        'state_file = "./state.json"',
                        "keep_last = 2",
                        "",
                        "[storage]",
                        'mode = "webdav"',
                        "",
                        "[storage.webdav]",
                        'base_url = "https://example.com/dav/"',
                        "upload_concurrency = 4",
                        "max_retries = 5",
                        "retry_backoff_seconds = 3",
                        "verify_after_upload = true",
                        'upload_temp_suffix = ".part"',
                        'cleanup_mode = "trash"',
                        "",
                        "[[repos]]",
                        'name = "owner/repo"',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            cfg = load_config(cfg_path)

            self.assertEqual(cfg.storage_mode, "webdav")
            self.assertEqual(cfg.webdav.upload_concurrency, 4)
            self.assertEqual(cfg.webdav.max_retries, 5)
            self.assertEqual(cfg.webdav.retry_backoff_seconds, 3)
            self.assertTrue(cfg.webdav.verify_after_upload)
            self.assertEqual(cfg.webdav.upload_temp_suffix, ".part")
            self.assertEqual(cfg.webdav.cleanup_mode, "trash")


if __name__ == "__main__":
    unittest.main()
