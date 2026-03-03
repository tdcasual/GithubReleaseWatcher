from __future__ import annotations

import threading
from typing import Any


class MetricsRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._api_request_total = 0
        self._api_last_latency_ms = 0.0
        self._queue_enqueue_total = 0
        self._queue_rejected_total = 0
        self._queue_deduplicated_total = 0
        self._queue_pending_current = 0
        self._queue_pending_peak = 0
        self._queue_pending_buckets: dict[str, int] = {"0": 0, "1": 0, "2_3": 0, "4_plus": 0}
        self._run_durations_ms: list[float] = []
        self._run_duration_sample_cap = 200
        self._recent_failure_types: list[str] = []
        self._failure_sample_cap = 100
        self._scheduler_lag_seconds = 0.0

    def record_api_request(self, latency_ms: float) -> None:
        with self._lock:
            self._api_request_total += 1
            self._api_last_latency_ms = max(0.0, float(latency_ms))

    def inc_queue_enqueue(self) -> None:
        with self._lock:
            self._queue_enqueue_total += 1

    def inc_queue_rejected(self) -> None:
        with self._lock:
            self._queue_rejected_total += 1

    def inc_queue_deduplicated(self) -> None:
        with self._lock:
            self._queue_deduplicated_total += 1

    def observe_queue_pending(self, depth: int) -> None:
        value = max(0, int(depth))
        with self._lock:
            self._queue_pending_current = value
            if value > self._queue_pending_peak:
                self._queue_pending_peak = value

            if value <= 0:
                bucket = "0"
            elif value == 1:
                bucket = "1"
            elif value <= 3:
                bucket = "2_3"
            else:
                bucket = "4_plus"
            self._queue_pending_buckets[bucket] = int(self._queue_pending_buckets.get(bucket, 0)) + 1

    def record_run_outcome(self, *, duration_ms: float, exit_code: int | None, error: str | None) -> None:
        safe_duration = max(0.0, float(duration_ms))
        with self._lock:
            self._run_durations_ms.append(safe_duration)
            if len(self._run_durations_ms) > self._run_duration_sample_cap:
                self._run_durations_ms = self._run_durations_ms[-self._run_duration_sample_cap :]

            failure_type: str | None = None
            if isinstance(error, str) and error.strip():
                failure_type = "exception"
            elif isinstance(exit_code, int) and exit_code != 0:
                failure_type = "exit_code_nonzero"

            if failure_type is not None:
                self._recent_failure_types.append(failure_type)
                if len(self._recent_failure_types) > self._failure_sample_cap:
                    self._recent_failure_types = self._recent_failure_types[-self._failure_sample_cap :]

    def set_scheduler_lag_seconds(self, value: float) -> None:
        with self._lock:
            self._scheduler_lag_seconds = max(0.0, float(value))

    @staticmethod
    def _quantile(values: list[float], q: float) -> float:
        if not values:
            return 0.0
        if len(values) == 1:
            return float(values[0])
        ordered = sorted(float(v) for v in values)
        idx = int(round((len(ordered) - 1) * float(q)))
        idx = max(0, min(idx, len(ordered) - 1))
        return float(ordered[idx])

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            failure_counts: dict[str, int] = {}
            for item in self._recent_failure_types:
                failure_counts[item] = int(failure_counts.get(item, 0)) + 1

            return {
                "api_request_total": self._api_request_total,
                "api_last_latency_ms": round(self._api_last_latency_ms, 3),
                "queue_enqueue_total": self._queue_enqueue_total,
                "queue_rejected_total": self._queue_rejected_total,
                "queue_deduplicated_total": self._queue_deduplicated_total,
                "queue_pending_current": self._queue_pending_current,
                "queue_pending_peak": self._queue_pending_peak,
                "queue_pending_buckets": dict(self._queue_pending_buckets),
                "run_duration_p50_ms": round(self._quantile(self._run_durations_ms, 0.50), 3),
                "run_duration_p95_ms": round(self._quantile(self._run_durations_ms, 0.95), 3),
                "recent_failure_types": failure_counts,
                "scheduler_lag_seconds": round(self._scheduler_lag_seconds, 3),
            }
