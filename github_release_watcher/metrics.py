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

    def set_scheduler_lag_seconds(self, value: float) -> None:
        with self._lock:
            self._scheduler_lag_seconds = max(0.0, float(value))

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "api_request_total": self._api_request_total,
                "api_last_latency_ms": round(self._api_last_latency_ms, 3),
                "queue_enqueue_total": self._queue_enqueue_total,
                "queue_rejected_total": self._queue_rejected_total,
                "scheduler_lag_seconds": round(self._scheduler_lag_seconds, 3),
            }
