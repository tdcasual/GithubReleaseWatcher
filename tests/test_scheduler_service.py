from __future__ import annotations

import unittest

from github_release_watcher.config import AppConfig, RepoConfig
from github_release_watcher.scheduler import SchedulerService


class _Now:
    def __init__(self, *values: float) -> None:
        self._values = list(values) or [0.0]
        self._idx = 0

    def __call__(self) -> float:
        if self._idx >= len(self._values):
            return self._values[-1]
        value = self._values[self._idx]
        self._idx += 1
        return value


class _Rng:
    def __init__(self, result: float) -> None:
        self.result = result
        self.calls: list[tuple[float, float]] = []

    def uniform(self, low: float, high: float) -> float:
        self.calls.append((low, high))
        return self.result


class SchedulerServiceTests(unittest.TestCase):
    def test_init_schedule_includes_only_enabled_repos(self) -> None:
        cfg = AppConfig(interval_seconds=120, repos=[RepoConfig("owner/repo"), RepoConfig("owner/skip", enabled=False)])
        svc = SchedulerService(now_seconds=_Now(1000.0))

        svc.set_enabled(True)
        svc.init_schedule(cfg, run_immediately=True)

        self.assertEqual(svc.repo_next_run_at, {"owner/repo": 1000.0})
        self.assertEqual(svc.next_run_at, 1000.0)

    def test_sync_schedule_reconciles_repo_set(self) -> None:
        cfg = AppConfig(interval_seconds=120, repos=[RepoConfig("owner/old")])
        svc = SchedulerService(now_seconds=_Now(1000.0, 2000.0))
        svc.init_schedule(cfg, run_immediately=False)
        self.assertEqual(svc.repo_next_run_at, {"owner/old": 1120.0})

        cfg.repos = [RepoConfig("owner/new")]
        svc.sync_schedule(cfg)

        self.assertEqual(svc.repo_next_run_at, {"owner/new": 2000.0})
        self.assertEqual(svc.next_run_at, 2000.0)

    def test_compute_next_run_uses_network_backoff_window(self) -> None:
        cfg = AppConfig(interval_seconds=120, repos=[RepoConfig("owner/repo")])
        rng = _Rng(9999.0)
        svc = SchedulerService(now_seconds=_Now(0.0), rng=rng)

        next_run = svc.compute_next_repo_run_at(
            cfg,
            {"stats": {"last_check_ok": False, "last_error_type": "network"}},
            now=10.0,
        )

        self.assertEqual(next_run, 10009.0)
        self.assertEqual(rng.calls, [(7200.0, 21600.0)])

    def test_poll_and_defer_repo(self) -> None:
        cfg = AppConfig(interval_seconds=120, repos=[RepoConfig("owner/a"), RepoConfig("owner/b")])
        svc = SchedulerService(now_seconds=_Now(100.0))
        svc.init_schedule(cfg, run_immediately=True)
        svc.repo_next_run_at["owner/a"] = 80.0
        svc.repo_next_run_at["owner/b"] = 95.0

        due_repo, next_run = svc.poll_due_repo(now=100.0, run_busy=False)
        self.assertEqual(due_repo, "owner/a")
        self.assertEqual(next_run, 80.0)

        svc.defer_repo("owner/a", now=100.0, seconds=60.0)
        self.assertEqual(svc.repo_next_run_at["owner/a"], 160.0)
        self.assertEqual(svc.next_run_at, 95.0)


if __name__ == "__main__":
    unittest.main()
