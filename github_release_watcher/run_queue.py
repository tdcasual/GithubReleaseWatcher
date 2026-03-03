from __future__ import annotations

import queue
import threading
from datetime import datetime, timezone
from typing import Any, Callable

from .metrics import MetricsRegistry


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class RunQueueService:
    def __init__(
        self,
        *,
        lock: threading.RLock | None = None,
        now_iso: Callable[[], str] | None = None,
        metrics: MetricsRegistry | None = None,
        max_pending: int = 8,
    ):
        self._lock = lock if lock is not None else threading.RLock()
        self._now_iso = now_iso or _utc_now_iso
        self._metrics = metrics
        self._queue: queue.Queue[dict[str, Any]] = queue.Queue()
        self._max_pending = max(1, int(max_pending))
        self._pending_keys: set[str] = set()
        self._dequeued_key: str | None = None
        self._run_in_progress_key: str | None = None
        self._run_requested = False
        self._run_in_progress = False
        self._run_id = 0
        self._last_run: dict[str, Any] | None = None
        if self._metrics is not None:
            self._metrics.observe_queue_pending(0)

    @property
    def queue(self) -> queue.Queue[dict[str, Any]]:
        return self._queue

    @staticmethod
    def _request_key(*, repo_key: str | None, repo_keys: list[str] | None) -> str:
        if isinstance(repo_keys, list):
            normalized = sorted({str(x) for x in repo_keys if isinstance(x, str) and x.strip()})
            if normalized:
                return "repos:" + ",".join(normalized)
        if isinstance(repo_key, str) and repo_key.strip():
            return f"repo:{repo_key}"
        return "all"

    def enqueue_result(
        self,
        *,
        source: str,
        repo_key: str | None = None,
        repo_keys: list[str] | None = None,
    ) -> dict[str, Any]:
        request_key = self._request_key(repo_key=repo_key, repo_keys=repo_keys)
        with self._lock:
            if request_key in self._pending_keys or request_key == self._dequeued_key or request_key == self._run_in_progress_key:
                if self._metrics is not None:
                    self._metrics.inc_queue_deduplicated()
                return {"status": "deduplicated"}

            if len(self._pending_keys) >= self._max_pending:
                if self._metrics is not None:
                    self._metrics.inc_queue_rejected()
                return {"status": "rejected_overflow"}

            self._run_requested = True
            if self._metrics is not None:
                self._metrics.inc_queue_enqueue()
            task: dict[str, Any] = {"type": "run_once"}
            if repo_keys is not None:
                task["repo_keys"] = list(repo_keys)
            else:
                task["repo_key"] = repo_key
            task["dedupe_key"] = request_key
            self._queue.put(task)
            self._pending_keys.add(request_key)
            if self._metrics is not None:
                self._metrics.observe_queue_pending(len(self._pending_keys))

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
            return {"status": "accepted"}

    def try_pop_task(self, *, timeout: float = 0.5) -> dict[str, Any] | None:
        try:
            task = self._queue.get(timeout=timeout)
        except queue.Empty:
            return None
        with self._lock:
            dedupe_key = task.get("dedupe_key")
            if isinstance(dedupe_key, str):
                self._pending_keys.discard(dedupe_key)
                self._dequeued_key = dedupe_key
                if self._metrics is not None:
                    self._metrics.observe_queue_pending(len(self._pending_keys))
            self._run_requested = bool(self._pending_keys)
        return task

    def begin_run(self) -> int | None:
        with self._lock:
            if self._run_in_progress:
                return None

            self._run_in_progress = True
            self._run_in_progress_key = self._dequeued_key
            self._dequeued_key = None
            self._run_requested = bool(self._pending_keys)
            self._run_id += 1
            run_id = self._run_id

            if self._last_run is not None:
                self._last_run["id"] = run_id
                self._last_run["started_at"] = self._now_iso()

            return run_id

    def finish_run(self, *, exit_code: int | None, error: str | None) -> None:
        with self._lock:
            self._run_in_progress = False
            self._run_in_progress_key = None
            self._run_requested = bool(self._pending_keys)
            if self._last_run is not None:
                self._last_run["finished_at"] = self._now_iso()
                self._last_run["exit_code"] = exit_code
                self._last_run["error"] = error

    def is_busy(self) -> bool:
        with self._lock:
            return self._run_requested or self._run_in_progress or self._dequeued_key is not None

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "requested": self._run_requested,
                "in_progress": self._run_in_progress,
                "last": dict(self._last_run) if isinstance(self._last_run, dict) else None,
            }
