from __future__ import annotations

import http.client
import json
from pathlib import Path
import tempfile
import threading
import time

from github_release_watcher.webapp import AuthService, Handler, WatcherService, _Server


def test_webapp_handler_delegates_to_router_module() -> None:
    source = Path("github_release_watcher/webapp.py").read_text(encoding="utf-8")
    assert "from .webapp_api_router import handle_api_request" in source
    assert "handle_api_request(self, path, split)" in source


def _write_base_config(base: Path, *, storage_mode: str = "local") -> Path:
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
        ),
        encoding="utf-8",
    )
    return cfg_path


def _normalize_shape(value):
    if isinstance(value, dict):
        return {k: _normalize_shape(v) for k, v in sorted(value.items())}
    if isinstance(value, list):
        if not value:
            return []
        return [_normalize_shape(value[0])]
    return type(value).__name__


def _request_json(host: str, port: int, token: str, path: str) -> dict:
    conn = http.client.HTTPConnection(host, port, timeout=3)
    try:
        conn.request(
            "GET",
            path,
            headers={"Cookie": f"grw_session={token}"},
        )
        res = conn.getresponse()
        body = res.read().decode("utf-8")
        return json.loads(body)
    finally:
        conn.close()


def _assert_shape_matches_snapshot(snapshot_name: str, payload: dict) -> None:
    snapshot_path = Path("tests/snapshots") / snapshot_name
    expected = json.loads(snapshot_path.read_text(encoding="utf-8"))
    actual = _normalize_shape(payload)
    assert actual == expected


def test_api_shape_snapshots_status_config_logs_storage_health() -> None:
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        cfg_path = _write_base_config(base)
        app = WatcherService(cfg_path)
        app.set_credentials("tester", "pass")
        auth = AuthService(app)
        token = auth.create_session(app.auth_username())
        server = _Server(("127.0.0.1", 0), Handler, app=app, ui=False, auth=auth)
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True)
        thread.start()
        time.sleep(0.02)
        try:
            host, port = server.server_address
            status_payload = _request_json(str(host), int(port), token, "/api/v1/status")
            config_payload = _request_json(str(host), int(port), token, "/api/v1/config")
            logs_payload = _request_json(str(host), int(port), token, "/api/v1/logs")
            storage_health_payload = _request_json(str(host), int(port), token, "/api/v1/storage/health")

            _assert_shape_matches_snapshot("status_shape.json", status_payload)
            _assert_shape_matches_snapshot("config_shape.json", config_payload)
            _assert_shape_matches_snapshot("logs_shape.json", logs_payload)
            _assert_shape_matches_snapshot("storage_health_shape.json", storage_health_payload)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            app.shutdown()
