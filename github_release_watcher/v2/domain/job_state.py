from __future__ import annotations

_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "queued": {"running", "canceled"},
    "running": {"succeeded", "failed", "canceled"},
    "succeeded": set(),
    "failed": set(),
    "canceled": set(),
}

_EVENT_TO_STATUS = {
    "started": "running",
    "job_started": "running",
    "succeeded": "succeeded",
    "job_succeeded": "succeeded",
    "failed": "failed",
    "job_failed": "failed",
    "canceled": "canceled",
    "job_canceled": "canceled",
}


def target_status_for_event(event_type: str) -> str | None:
    return _EVENT_TO_STATUS.get(str(event_type or "").strip())


def assert_transition(current: str, nxt: str) -> None:
    if nxt not in _STATUS_TRANSITIONS.get(str(current or "").strip(), set()):
        raise ValueError(f"invalid transition: {current}->{nxt}")
