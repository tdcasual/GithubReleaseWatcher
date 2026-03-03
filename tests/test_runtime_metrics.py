from __future__ import annotations

import tempfile
from pathlib import Path

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


def test_snapshot_exposes_runtime_metrics() -> None:
    with tempfile.TemporaryDirectory() as td:
        cfg_path = _write_base_config(Path(td))
        app = WatcherService(cfg_path)
        snap = app.snapshot()

        assert "metrics" in snap
        metrics = snap["metrics"]
        assert "api_request_total" in metrics
        assert "queue_enqueue_total" in metrics
        assert "queue_rejected_total" in metrics
        assert "scheduler_lag_seconds" in metrics
