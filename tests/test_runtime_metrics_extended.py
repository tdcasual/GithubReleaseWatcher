from __future__ import annotations

import tempfile
from pathlib import Path

from github_release_watcher.metrics import MetricsRegistry
from github_release_watcher.webapp import WatcherService


def _write_base_config(base: Path) -> Path:
    cfg_path = base / "config.toml"
    cfg_path.write_text(
        "\n".join(
            [
                "interval_seconds = 60",
                'download_dir = "./downloads"',
                'state_file = "./state.json"',
                "keep_last = 1",
                "",
                "[[repos]]",
                'name = "owner/repo"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    return cfg_path


def test_metrics_registry_tracks_queue_depth_distribution() -> None:
    metrics = MetricsRegistry()
    metrics.observe_queue_pending(0)
    metrics.observe_queue_pending(1)
    metrics.observe_queue_pending(2)
    metrics.observe_queue_pending(4)

    snap = metrics.snapshot()
    assert snap["queue_pending_current"] == 4
    assert snap["queue_pending_peak"] == 4
    assert snap["queue_pending_buckets"]["0"] >= 1
    assert snap["queue_pending_buckets"]["1"] >= 1
    assert snap["queue_pending_buckets"]["2_3"] >= 1
    assert snap["queue_pending_buckets"]["4_plus"] >= 1


def test_metrics_registry_tracks_run_duration_quantiles_and_failure_types() -> None:
    metrics = MetricsRegistry()
    metrics.record_run_outcome(duration_ms=120.0, exit_code=0, error=None)
    metrics.record_run_outcome(duration_ms=480.0, exit_code=2, error=None)
    metrics.record_run_outcome(duration_ms=260.0, exit_code=None, error="ValueError: bad payload")

    snap = metrics.snapshot()
    assert snap["run_duration_p50_ms"] >= 120.0
    assert snap["run_duration_p95_ms"] >= snap["run_duration_p50_ms"]
    assert snap["recent_failure_types"]["exit_code_nonzero"] >= 1
    assert snap["recent_failure_types"]["exception"] >= 1


def test_snapshot_exposes_extended_runtime_metrics_fields() -> None:
    with tempfile.TemporaryDirectory() as td:
        cfg_path = _write_base_config(Path(td))
        app = WatcherService(cfg_path)
        snap = app.snapshot()
        metrics = snap["metrics"]

        assert "queue_pending_current" in metrics
        assert "queue_pending_peak" in metrics
        assert "queue_pending_buckets" in metrics
        assert "run_duration_p50_ms" in metrics
        assert "run_duration_p95_ms" in metrics
        assert "recent_failure_types" in metrics
