#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

python3 - <<'PY'
from __future__ import annotations

import http.client
import json
import tempfile
import threading
import time
from pathlib import Path

from github_release_watcher.webapp import AuthService, Handler, WatcherService, _Server


def write_config(base: Path) -> Path:
    config_path = base / "config.toml"
    config_path.write_text(
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
    return config_path


def json_request(
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


with tempfile.TemporaryDirectory() as td:
    base = Path(td)
    app = WatcherService(write_config(base))
    app.set_credentials("tester", "pass")
    auth = AuthService(app)
    server = _Server(("127.0.0.1", 0), Handler, app=app, ui=False, auth=auth)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True)
    thread.start()
    time.sleep(0.02)

    conn: http.client.HTTPConnection | None = None
    try:
        host, port = server.server_address
        conn = http.client.HTTPConnection(str(host), int(port), timeout=5)

        login_code, login_payload, login_res = json_request(
            conn,
            method="POST",
            path="/api/v1/login",
            payload={"username": "tester", "password": "pass"},
        )
        assert login_code == 200, f"login status={login_code} payload={login_payload}"
        assert login_payload.get("ok") is True, f"unexpected login payload={login_payload}"
        set_cookie = login_res.getheader("Set-Cookie") or ""
        assert "grw_session=" in set_cookie, f"missing session cookie header={set_cookie!r}"
        token = set_cookie.split("grw_session=", 1)[1].split(";", 1)[0]
        assert token, "empty session token"
        print("[smoke] login ok")

        state_code, state_payload, _ = json_request(conn, method="GET", path="/api/v1/state", token=token)
        assert state_code == 200, f"state status={state_code} payload={state_payload}"
        assert isinstance(state_payload.get("state"), dict), f"state payload invalid={state_payload}"
        assert isinstance(state_payload["state"].get("repos"), dict), f"state.repos invalid={state_payload}"
        print("[smoke] state ok")

        run_code, run_payload, _ = json_request(conn, method="POST", path="/api/v1/run", token=token, payload={})
        assert run_code == 200, f"run status={run_code} payload={run_payload}"
        assert run_payload.get("queue_status") == "accepted", f"run payload invalid={run_payload}"
        assert run_payload.get("queued") is True, f"run payload invalid={run_payload}"
        print("[smoke] run ok")

        repos_code, repos_payload, _ = json_request(conn, method="GET", path="/api/v1/repos", token=token)
        assert repos_code == 200, f"repos status={repos_code} payload={repos_payload}"
        items = repos_payload.get("items")
        assert isinstance(items, list), f"repos payload invalid={repos_payload}"
        assert any(item.get("key") == "owner/repo" for item in items), f"repo missing in payload={repos_payload}"
        print("[smoke] repos ok")
    finally:
        if conn is not None:
            conn.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        app.shutdown()

print("[smoke] api flow ok")
PY
