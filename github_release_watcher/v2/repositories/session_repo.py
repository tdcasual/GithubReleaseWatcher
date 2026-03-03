from __future__ import annotations

from pathlib import Path

from ..db import connect_db


def create_session(*, db_path: Path, token: str, username: str, expires_at: float, created_at: str) -> None:
    conn = connect_db(db_path)
    try:
        conn.execute(
            "INSERT INTO sessions(token, username, expires_at, created_at) VALUES (?, ?, ?, ?)",
            (token, username, float(expires_at), created_at),
        )
        conn.commit()
    finally:
        conn.close()


def get_session(*, db_path: Path, token: str) -> dict[str, object] | None:
    conn = connect_db(db_path)
    try:
        row = conn.execute(
            "SELECT token, username, expires_at, created_at FROM sessions WHERE token = ?",
            (token,),
        ).fetchone()
        if row is None:
            return None
        return {
            "token": row["token"],
            "username": row["username"],
            "expires_at": float(row["expires_at"]),
            "created_at": row["created_at"],
        }
    finally:
        conn.close()


def delete_session(*, db_path: Path, token: str) -> None:
    conn = connect_db(db_path)
    try:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
        conn.commit()
    finally:
        conn.close()


def delete_expired_sessions(*, db_path: Path, now_epoch: float) -> None:
    conn = connect_db(db_path)
    try:
        conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (float(now_epoch),))
        conn.commit()
    finally:
        conn.close()
