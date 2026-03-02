from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import threading
import time
from typing import Any, Protocol


class _LoginVerifier(Protocol):
    def verify_login(self, username: str, password: str) -> bool:
        ...


def _pbkdf2_hash(password: str, *, salt_hex: str, iterations: int) -> str:
    salt = bytes.fromhex(salt_hex)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
    return dk.hex()


def _default_auth_config() -> dict[str, Any]:
    # Default credentials: admin/admin
    salt_hex = secrets.token_bytes(16).hex()
    iterations = 200_000
    return {
        "username": "admin",
        "salt": salt_hex,
        "iterations": iterations,
        "password_hash": _pbkdf2_hash("admin", salt_hex=salt_hex, iterations=iterations),
        "must_change_password": True,
    }


def _load_auth_config(overrides: dict[str, Any]) -> dict[str, Any]:
    auth = overrides.get("auth", {}) if isinstance(overrides.get("auth"), dict) else {}
    username = auth.get("username")
    salt = auth.get("salt")
    iterations = auth.get("iterations")
    password_hash = auth.get("password_hash")

    if not isinstance(username, str) or not username.strip():
        return _default_auth_config()
    if not isinstance(salt, str) or not re.fullmatch(r"[0-9a-f]{16,128}", salt):
        return _default_auth_config()
    if not isinstance(iterations, int) or iterations < 50_000 or iterations > 2_000_000:
        return _default_auth_config()
    if not isinstance(password_hash, str) or not re.fullmatch(r"[0-9a-f]{32,128}", password_hash):
        return _default_auth_config()

    return {
        "username": username.strip(),
        "salt": salt,
        "iterations": int(iterations),
        "password_hash": password_hash,
        "must_change_password": False,
    }


def _verify_password(password: str, auth_config: dict[str, Any]) -> bool:
    try:
        expected = str(auth_config["password_hash"])
        got = _pbkdf2_hash(password, salt_hex=str(auth_config["salt"]), iterations=int(auth_config["iterations"]))
        return hmac.compare_digest(expected, got)
    except Exception:
        return False


class AuthService:
    def __init__(self, app: _LoginVerifier, *, session_ttl_seconds: int = 12 * 60 * 60):
        self._app = app
        self._ttl = max(60, int(session_ttl_seconds))
        self._lock = threading.Lock()
        self._sessions: dict[str, float] = {}
        self._failed_attempts: dict[str, list[float]] = {}
        self._max_failures = 6
        self._window_seconds = 5 * 60

    def _prune_failures_locked(self, key: str, *, now: float) -> list[float]:
        entries = [x for x in self._failed_attempts.get(key, []) if now - x <= self._window_seconds]
        if entries:
            self._failed_attempts[key] = entries
        else:
            self._failed_attempts.pop(key, None)
        return entries

    def _record_failure(self, key: str) -> None:
        now = time.time()
        with self._lock:
            entries = self._prune_failures_locked(key, now=now)
            entries.append(now)
            self._failed_attempts[key] = entries

    def _clear_failures(self, key: str) -> None:
        with self._lock:
            self._failed_attempts.pop(key, None)

    def _is_rate_limited(self, key: str) -> bool:
        now = time.time()
        with self._lock:
            entries = self._prune_failures_locked(key, now=now)
            return len(entries) >= self._max_failures

    def create_session(self, username: str) -> str:
        token = secrets.token_urlsafe(32)
        expires_at = time.time() + self._ttl
        with self._lock:
            self._sessions[token] = expires_at
        return token

    def delete_session(self, token: str | None) -> None:
        if not token:
            return
        with self._lock:
            self._sessions.pop(token, None)

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

    def login(self, username: str, password: str, client_key: str | None = None) -> tuple[str | None, str | None]:
        key = str(client_key or "").strip() or "unknown"
        if self._is_rate_limited(key):
            return None, "rate_limited"
        if not self._app.verify_login(username, password):
            self._record_failure(key)
            if self._is_rate_limited(key):
                return None, "rate_limited"
            return None, "invalid_credentials"
        self._clear_failures(key)
        return self.create_session(username), None

    @staticmethod
    def get_token_from_cookie(cookie_header: str | None) -> str | None:
        if not cookie_header:
            return None
        parts = [p.strip() for p in cookie_header.split(";") if p.strip()]
        for part in parts:
            if part.startswith("grw_session="):
                return part.split("=", 1)[1].strip() or None
        return None
