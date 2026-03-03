from __future__ import annotations

from pathlib import Path
import tempfile

from github_release_watcher.v2.auth import V2AuthService, hash_password, verify_password


def test_password_hash_roundtrip() -> None:
    digest = hash_password("pass123")
    assert digest != "pass123"
    assert verify_password("pass123", digest)


def test_login_requires_persisted_session() -> None:
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "v2.sqlite3"
        from github_release_watcher.v2.db import init_db

        init_db(db_path)
        svc = V2AuthService(db_path=db_path, username="tester", password="pass")
        token = svc.login(username="tester", password="pass")
        assert isinstance(token, str)
        # New instance still validates session from sqlite
        svc2 = V2AuthService(db_path=db_path, username="tester", password="pass")
        assert svc2.is_valid(token)
