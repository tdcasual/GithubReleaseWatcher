from __future__ import annotations

import hmac
import secrets
import threading
import time


class V2AuthService:
    def __init__(self, *, username: str, password: str, session_ttl_seconds: int = 12 * 60 * 60) -> None:
        user = str(username or "").strip()
        if not user:
            raise ValueError("auth username required")
        if not isinstance(password, str) or password == "":
            raise ValueError("auth password required")
        self._username = user
        self._password = password
        self._ttl = max(60, int(session_ttl_seconds))
        self._lock = threading.Lock()
        self._sessions: dict[str, float] = {}

    @property
    def username(self) -> str:
        return self._username

    def login(self, *, username: str, password: str) -> str | None:
        if not hmac.compare_digest(str(username or "").strip(), self._username):
            return None
        if not hmac.compare_digest(str(password or ""), self._password):
            return None
        token = secrets.token_urlsafe(32)
        expires_at = time.time() + self._ttl
        with self._lock:
            self._sessions[token] = expires_at
        return token

    def is_valid(self, token: str | None) -> bool:
        if not token:
            return False
        now = time.time()
        with self._lock:
            expires_at = self._sessions.get(token)
            if expires_at is None:
                return False
            if now >= expires_at:
                self._sessions.pop(token, None)
                return False
            return True

    def delete_session(self, token: str | None) -> None:
        if not token:
            return
        with self._lock:
            self._sessions.pop(token, None)
