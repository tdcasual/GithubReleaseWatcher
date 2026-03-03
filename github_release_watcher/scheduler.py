from __future__ import annotations

import random
import time
from typing import Any, Callable

from .config import AppConfig
from .metrics import MetricsRegistry
from .webapp_overrides import _repo_key_from_spec


class SchedulerService:
    def __init__(
        self,
        *,
        now_seconds: Callable[[], float] | None = None,
        rng: random.Random | None = None,
        metrics: MetricsRegistry | None = None,
    ):
        self._now_seconds = now_seconds or time.time
        self._rng = rng or random.Random()
        self._metrics = metrics
        self._enabled = True
        self._next_run_at: float | None = None
        self._repo_next_run_at: dict[str, float] = {}

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def next_run_at(self) -> float | None:
        return self._next_run_at

    @property
    def repo_next_run_at(self) -> dict[str, float]:
        return self._repo_next_run_at

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)
        self._refresh_next_run_at()

    def init_schedule(self, config: AppConfig | None, *, run_immediately: bool) -> None:
        self._repo_next_run_at.clear()
        if config is None:
            self._next_run_at = None
            return

        now = self._now_seconds()
        base = max(60, int(config.interval_seconds))
        for key in self._enabled_repo_keys(config):
            self._repo_next_run_at[key] = now if run_immediately else now + base
        self._refresh_next_run_at()

    def sync_schedule(self, config: AppConfig | None) -> None:
        if config is None:
            self._repo_next_run_at.clear()
            self._next_run_at = None
            return

        enabled_keys = set(self._enabled_repo_keys(config))
        now = self._now_seconds()
        for key in list(self._repo_next_run_at.keys()):
            if key not in enabled_keys:
                self._repo_next_run_at.pop(key, None)
        for key in enabled_keys:
            if key not in self._repo_next_run_at:
                self._repo_next_run_at[key] = now
        self._refresh_next_run_at()

    def recommended_interval_seconds(self, config: AppConfig, repo_state: dict[str, Any]) -> int:
        base = max(60, int(getattr(config, "interval_seconds", 172800) or 172800))
        update = repo_state.get("update", {}) if isinstance(repo_state.get("update"), dict) else {}
        median = update.get("median_interval_seconds")
        if isinstance(median, (int, float)) and float(median) > 0:
            return max(base, int(float(median) * 1.1))
        return base

    def compute_next_repo_run_at(self, config: AppConfig, repo_state: dict[str, Any], *, now: float) -> float:
        interval = float(self.recommended_interval_seconds(config, repo_state))
        stats = repo_state.get("stats", {}) if isinstance(repo_state.get("stats"), dict) else {}
        ok = stats.get("last_check_ok")
        last_error_type = str(stats.get("last_error_type") or "")
        had_net = bool(stats.get("last_check_had_network_error", False))

        if ok is True:
            return now + interval

        if last_error_type == "network" or had_net:
            retry_seconds = float(self._rng.uniform(2 * 3600, 6 * 3600))
            return now + retry_seconds

        return now + interval

    def update_processed_repo_runs(
        self,
        config: AppConfig,
        repos_state: dict[str, Any],
        *,
        processed_keys: list[str],
        now: float,
    ) -> None:
        for key in processed_keys:
            repo_state = repos_state.get(key, {}) if isinstance(repos_state.get(key), dict) else {}
            self._repo_next_run_at[key] = self.compute_next_repo_run_at(config, repo_state, now=now)
        self.sync_schedule(config)

    def poll_due_repo(self, *, now: float, run_busy: bool) -> tuple[str | None, float | None]:
        if not self._enabled or not self._repo_next_run_at:
            self._next_run_at = None
            if self._metrics is not None:
                self._metrics.set_scheduler_lag_seconds(0.0)
            return None, None

        next_run = min(self._repo_next_run_at.values())
        if self._metrics is not None:
            self._metrics.set_scheduler_lag_seconds(max(0.0, float(now - next_run)))
        due_repo: str | None = None
        if not run_busy:
            for key, ts in self._repo_next_run_at.items():
                if ts <= now and (due_repo is None or ts < self._repo_next_run_at.get(due_repo, ts)):
                    due_repo = key

        self._next_run_at = next_run
        return due_repo, next_run

    def defer_repo(self, repo_key: str, *, now: float, seconds: float = 60.0) -> None:
        self._repo_next_run_at[repo_key] = now + seconds
        self._refresh_next_run_at()

    def _refresh_next_run_at(self) -> None:
        if not self._enabled or not self._repo_next_run_at:
            self._next_run_at = None
            return
        self._next_run_at = min(self._repo_next_run_at.values())

    @staticmethod
    def _enabled_repo_keys(config: AppConfig) -> list[str]:
        keys: list[str] = []
        for repo_cfg in config.repos:
            if not bool(getattr(repo_cfg, "enabled", True)):
                continue
            try:
                keys.append(_repo_key_from_spec(repo_cfg.name))
            except Exception:
                keys.append(repo_cfg.name)
        return keys
