from __future__ import annotations

import http.client
import json
import tempfile
import threading
import time
from pathlib import Path

from github_release_watcher.webapp import AuthService, Handler, WatcherService, _Server


def _write_base_config(base: Path) -> Path:
    cfg_path = base / "config.toml"
    cfg_path.write_text(
        "\n".join(
            [
                "interval_seconds = 60",
                'download_dir = "./downloads"',
                'state_file = "./state.json"',
                "keep_last = 1",
                "",
                "[[repos]]",
                'name = "owner/repo"',
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return cfg_path


def _json_request(
    conn: http.client.HTTPConnection,
    *,
    method: str,
    path: str,
    token: str | None = None,
    payload: dict | None = None,
) -> tuple[int, dict, http.client.HTTPResponse]:
    headers: dict[str, str] = {}
    body = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload).encode("utf-8")
    if token:
        headers["Cookie"] = f"grw_session={token}"

    conn.request(method, path, body=body, headers=headers)
    res = conn.getresponse()
    raw = res.read().decode("utf-8")
    data = json.loads(raw) if raw else {}
    return res.status, data, res


def test_minimal_api_end_to_end_flow() -> None:
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        cfg_path = _write_base_config(base)
        app = WatcherService(cfg_path)
        app.set_credentials("tester", "pass")
        auth = AuthService(app)
        server = _Server(("127.0.0.1", 0), Handler, app=app, ui=False, auth=auth)
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True)
        thread.start()
        time.sleep(0.02)
        conn: http.client.HTTPConnection | None = None
        try:
            host, port = server.server_address
            conn = http.client.HTTPConnection(str(host), int(port), timeout=3)

            login_code, login_payload, login_res = _json_request(
                conn,
                method="POST",
                path="/api/v1/login",
                payload={"username": "tester", "password": "pass"},
            )
            assert login_code == 200
            assert login_payload.get("ok") is True
            set_cookie = login_res.getheader("Set-Cookie") or ""
            assert "grw_session=" in set_cookie
            token = set_cookie.split("grw_session=", 1)[1].split(";", 1)[0]
            assert token

            state_code, state_payload, _ = _json_request(conn, method="GET", path="/api/v1/state", token=token)
            assert state_code == 200
            assert isinstance(state_payload.get("state"), dict)
            assert isinstance(state_payload["state"].get("repos"), dict)

            run_code, run_payload, _ = _json_request(conn, method="POST", path="/api/v1/run", token=token, payload={})
            assert run_code == 200
            assert run_payload.get("queue_status") == "accepted"
            assert run_payload.get("queued") is True

            repos_code, repos_payload, _ = _json_request(conn, method="GET", path="/api/v1/repos", token=token)
            assert repos_code == 200
            assert isinstance(repos_payload.get("items"), list)
            assert any(item.get("key") == "owner/repo" for item in repos_payload["items"])
        finally:
            if conn is not None:
                conn.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            app.shutdown()


def test_smoke_api_flow_script_exists() -> None:
    script = Path("scripts/qa/smoke_api_flow.sh")
    assert script.exists()
    assert script.read_text(encoding="utf-8").startswith("#!/usr/bin/env bash")
