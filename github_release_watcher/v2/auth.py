from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path

from .repositories.session_repo import create_session, delete_expired_sessions, delete_session, get_session


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def hash_password(raw: str) -> str:
    if not isinstance(raw, str) or raw == "":
        raise ValueError("auth password required")
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", raw.encode("utf-8"), salt.encode("utf-8"), 200_000).hex()
    return f"{salt}${digest}"


def verify_password(raw: str, stored: str) -> bool:
    if not isinstance(stored, str) or "$" not in stored:
        return False
    try:
        salt, digest = stored.split("$", 1)
    except ValueError:
        return False
    check = hashlib.pbkdf2_hmac("sha256", str(raw or "").encode("utf-8"), salt.encode("utf-8"), 200_000).hex()
    return hmac.compare_digest(check, digest)


class V2AuthService:
    def __init__(self, *, db_path: Path, username: str, password: str, session_ttl_seconds: int = 12 * 60 * 60) -> None:
        user = str(username or "").strip()
        if not user:
            raise ValueError("auth username required")
        self._db_path = Path(db_path)
        self._username = user
        self._password_hash = hash_password(password)
        self._ttl = max(60, int(session_ttl_seconds))

    @property
    def username(self) -> str:
        return self._username

    def login(self, *, username: str, password: str) -> str | None:
        if not hmac.compare_digest(str(username or "").strip(), self._username):
            return None
        if not verify_password(str(password or ""), self._password_hash):
            return None

        token = secrets.token_urlsafe(32)
        now_epoch = time.time()
        create_session(
            db_path=self._db_path,
            token=token,
            username=self._username,
            expires_at=now_epoch + self._ttl,
            created_at=_now_iso(),
        )
        return token

    def is_valid(self, token: str | None) -> bool:
        if not token:
            return False
        now_epoch = time.time()
        delete_expired_sessions(db_path=self._db_path, now_epoch=now_epoch)
        row = get_session(db_path=self._db_path, token=token)
        if row is None:
            return False
        expires_at = float(row.get("expires_at") or 0.0)
        if now_epoch >= expires_at:
            delete_session(db_path=self._db_path, token=token)
            return False
        return True

    def delete_session(self, token: str | None) -> None:
        if not token:
            return
        delete_session(db_path=self._db_path, token=token)
