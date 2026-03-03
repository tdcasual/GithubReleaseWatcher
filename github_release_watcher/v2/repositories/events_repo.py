from __future__ import annotations

import sqlite3


def insert_event(
    conn: sqlite3.Connection,
    *,
    job_id: str,
    event_type: str,
    payload_json: str,
    created_at: str,
) -> int:
    conn.execute(
        "INSERT INTO events(job_id, event_type, payload_json, created_at) VALUES (?, ?, ?, ?)",
        (job_id, event_type, payload_json, created_at),
    )
    row = conn.execute("SELECT last_insert_rowid()").fetchone()
    return int(row[0]) if row is not None else 0


def list_events(conn: sqlite3.Connection, *, job_id: str | None, limit: int) -> list[sqlite3.Row]:
    if isinstance(job_id, str) and job_id.strip():
        return conn.execute(
            """
            SELECT id, job_id, event_type, payload_json, created_at
            FROM events
            WHERE job_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (job_id.strip(), limit),
        ).fetchall()

    return conn.execute(
        """
        SELECT id, job_id, event_type, payload_json, created_at
        FROM events
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
