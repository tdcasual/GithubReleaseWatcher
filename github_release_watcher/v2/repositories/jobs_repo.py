from __future__ import annotations

import sqlite3


def insert_job(
    conn: sqlite3.Connection,
    *,
    job_id: str,
    kind: str,
    payload_json: str,
    created_at: str,
) -> None:
    conn.execute(
        "INSERT INTO jobs(id, kind, status, payload_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        (job_id, kind, "queued", payload_json, created_at, created_at),
    )


def get_job(conn: sqlite3.Connection, *, job_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT id, status FROM jobs WHERE id = ?", (job_id,)).fetchone()


def update_job_status(
    conn: sqlite3.Connection,
    *,
    job_id: str,
    status: str,
    updated_at: str,
    error_text: str | None,
) -> None:
    conn.execute(
        "UPDATE jobs SET status = ?, updated_at = ?, error_text = ? WHERE id = ?",
        (status, updated_at, error_text, job_id),
    )


def list_jobs(conn: sqlite3.Connection, *, limit: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT id, kind, status, payload_json, created_at, updated_at, error_text FROM jobs ORDER BY created_at DESC, id DESC LIMIT ?",
        (limit,),
    ).fetchall()
