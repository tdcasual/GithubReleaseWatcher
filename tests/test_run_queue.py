from __future__ import annotations

import unittest

from github_release_watcher.run_queue import RunQueueService


class _Now:
    def __init__(self) -> None:
        self._i = 0

    def __call__(self) -> str:
        self._i += 1
        return f"2026-03-02T00:00:0{self._i}+00:00"


class RunQueueServiceTests(unittest.TestCase):
    def test_enqueue_result_creates_task_and_pending_run(self) -> None:
        now = _Now()
        svc = RunQueueService(now_iso=now)

        result = svc.enqueue_result(source="api", repo_key="owner/repo")

        self.assertEqual(result["status"], "accepted")
        self.assertNotIn("queued", result)
        task = svc.queue.get_nowait()
        self.assertEqual(task.get("type"), "run_once")
        self.assertEqual(task.get("repo_key"), "owner/repo")
        self.assertIsNone(task.get("repo_keys"))

        snap = svc.snapshot()
        self.assertTrue(snap["requested"])
        self.assertFalse(snap["in_progress"])
        self.assertEqual(snap["last"]["id"], 1)
        self.assertEqual(snap["last"]["queued_at"], "2026-03-02T00:00:01+00:00")
        self.assertIsNone(snap["last"]["started_at"])

    def test_enqueue_result_deduplicates_same_request(self) -> None:
        svc = RunQueueService(now_iso=_Now(), max_pending=4)

        first = svc.enqueue_result(source="api", repo_key="owner/repo")
        second = svc.enqueue_result(source="api", repo_key="owner/repo")

        self.assertEqual(first["status"], "accepted")
        self.assertEqual(second["status"], "deduplicated")
        self.assertNotIn("queued", first)
        self.assertNotIn("queued", second)

    def test_enqueue_result_rejects_overflow(self) -> None:
        svc = RunQueueService(now_iso=_Now(), max_pending=1)

        first = svc.enqueue_result(source="api", repo_key="owner/repo")
        second = svc.enqueue_result(source="api", repo_key="owner/another")

        self.assertEqual(first["status"], "accepted")
        self.assertEqual(second["status"], "rejected_overflow")
        self.assertNotIn("queued", first)
        self.assertNotIn("queued", second)

    def test_enqueue_result_allows_batch_and_single_mix(self) -> None:
        svc = RunQueueService(now_iso=_Now(), max_pending=4)

        batch = svc.enqueue_result(source="api", repo_keys=["owner/repo", "owner/another"])
        single = svc.enqueue_result(source="api", repo_key="owner/repo")

        self.assertEqual(batch["status"], "accepted")
        self.assertEqual(single["status"], "accepted")

        first = svc.queue.get_nowait()
        second = svc.queue.get_nowait()
        self.assertEqual(first.get("repo_keys"), ["owner/repo", "owner/another"])
        self.assertIsNone(first.get("repo_key"))
        self.assertEqual(second.get("repo_key"), "owner/repo")
        self.assertIsNone(second.get("repo_keys"))

    def test_begin_and_finish_run_updates_state(self) -> None:
        now = _Now()
        svc = RunQueueService(now_iso=now)
        self.assertEqual(
            svc.enqueue_result(source="manual", repo_keys=["owner/repo", "owner/another"])["status"],
            "accepted",
        )
        task = svc.try_pop_task(timeout=0.001)
        self.assertIsNotNone(task)

        run_id = svc.begin_run()

        self.assertEqual(run_id, 1)
        mid = svc.snapshot()
        self.assertFalse(mid["requested"])
        self.assertTrue(mid["in_progress"])
        self.assertEqual(mid["last"]["started_at"], "2026-03-02T00:00:02+00:00")
        self.assertEqual(mid["last"]["repos"], ["owner/repo", "owner/another"])

        svc.finish_run(exit_code=0, error=None)
        done = svc.snapshot()
        self.assertFalse(done["in_progress"])
        self.assertEqual(done["last"]["finished_at"], "2026-03-02T00:00:03+00:00")
        self.assertEqual(done["last"]["exit_code"], 0)
        self.assertIsNone(done["last"]["error"])

    def test_try_pop_task_returns_none_when_empty(self) -> None:
        svc = RunQueueService(now_iso=_Now())
        self.assertIsNone(svc.try_pop_task(timeout=0.001))


if __name__ == "__main__":
    unittest.main()
