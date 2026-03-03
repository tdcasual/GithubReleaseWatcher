from __future__ import annotations

from pathlib import Path
import tempfile

from github_release_watcher.v2.db import init_db


def test_job_domain_transition_mapping() -> None:
    from github_release_watcher.v2.domain.job_state import assert_transition, target_status_for_event

    assert target_status_for_event("started") == "running"
    assert target_status_for_event("job_succeeded") == "succeeded"
    assert target_status_for_event("unknown") is None

    assert_transition("queued", "running")

    try:
        assert_transition("queued", "succeeded")
    except ValueError as exc:
        assert "invalid transition" in str(exc)
    else:
        raise AssertionError("expected ValueError for invalid transition")


def test_jobs_service_roundtrip() -> None:
    from github_release_watcher.v2.services.jobs_service import JobsService

    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "v2.sqlite3"
        init_db(db_path)
        svc = JobsService(db_path)

        created = svc.enqueue_job(kind="run_repos", payload={"repos": ["owner/repo"]})
        assert created["status"] == "queued"

        started = svc.append_event(job_id=created["id"], event_type="started", payload={})
        assert started["event_type"] == "started"

        done = svc.append_event(job_id=created["id"], event_type="succeeded", payload={})
        assert done["event_type"] == "succeeded"

        jobs = svc.list_jobs(limit=10)
        target = [x for x in jobs if x["id"] == created["id"]][0]
        assert target["status"] == "succeeded"

        events = svc.list_events(job_id=created["id"], limit=10)
        assert len(events) >= 2
