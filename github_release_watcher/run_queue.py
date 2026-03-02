from __future__ import annotations

import queue
import threading
from datetime import datetime, timezone
from typing import Any, Callable


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class RunQueueService:
    def __init__(
        self,
        *,
        lock: threading.RLock | None = None,
        now_iso: Callable[[], str] | None = None,
    ):
        self._lock = lock if lock is not None else threading.RLock()
        self._now_iso = now_iso or _utc_now_iso
        self._queue: queue.Queue[dict[str, Any]] = queue.Queue()
        self._run_requested = False
        self._run_in_progress = False
        self._run_id = 0
        self._last_run: dict[str, Any] | None = None

    @property
    def queue(self) -> queue.Queue[dict[str, Any]]:
        return self._queue

    def enqueue(self, *, source: str, repo_key: str | None = None, repo_keys: list[str] | None = None) -> bool:
        with self._lock:
            if self._run_requested or self._run_in_progress:
                return False

            self._run_requested = True
            task: dict[str, Any] = {"type": "run_once"}
            if repo_keys is not None:
                task["repo_keys"] = list(repo_keys)
            else:
                task["repo_key"] = repo_key
            self._queue.put(task)

            self._last_run = {
                "id": self._run_id + 1,
                "source": source,
                "repo": repo_key,
                "repos": list(repo_keys) if repo_keys is not None else None,
                "queued_at": self._now_iso(),
                "started_at": None,
                "finished_at": None,
                "exit_code": None,
                "error": None,
            }
            return True

    def try_pop_task(self, *, timeout: float = 0.5) -> dict[str, Any] | None:
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def begin_run(self) -> int | None:
        with self._lock:
            self._run_requested = False
            if self._run_in_progress:
                return None

            self._run_in_progress = True
            self._run_id += 1
            run_id = self._run_id

            if self._last_run is not None:
                self._last_run["id"] = run_id
                self._last_run["started_at"] = self._now_iso()

            return run_id

    def finish_run(self, *, exit_code: int | None, error: str | None) -> None:
        with self._lock:
            self._run_in_progress = False
            if self._last_run is not None:
                self._last_run["finished_at"] = self._now_iso()
                self._last_run["exit_code"] = exit_code
                self._last_run["error"] = error

    def is_busy(self) -> bool:
        with self._lock:
            return self._run_requested or self._run_in_progress

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "requested": self._run_requested,
                "in_progress": self._run_in_progress,
                "last": dict(self._last_run) if isinstance(self._last_run, dict) else None,
            }
