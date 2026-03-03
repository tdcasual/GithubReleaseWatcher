from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from github_release_watcher.config import AppConfig, load_config
from github_release_watcher.repo_query_service import RepoQueryService
from github_release_watcher.webapp_overrides import _repo_key_from_spec


def _write_config(base: Path) -> AppConfig:
    cfg_path = base / "config.toml"
    cfg_path.write_text(
        "\n".join(
            [
                "interval_seconds = 60",
                'download_dir = "./downloads"',
                'state_file = "./state.json"',
                "keep_last = 2",
                "",
                "[[repos]]",
                'name = "owner/repo"',
                "",
                "[[repos]]",
                'name = "owner/another"',
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return load_config(cfg_path)


def _service() -> RepoQueryService:
    return RepoQueryService(
        repo_key_from_spec=_repo_key_from_spec,
        recommended_interval_seconds=lambda _config, _repo_state: 123,
    )


def test_list_repo_summaries_and_get_repo_summary() -> None:
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        cfg = _write_config(base)
        cfg.state_file.write_text(
            json.dumps(
                {
                    "version": 1,
                    "repos": {
                        "owner/repo": {
                            "stats": {"current_tag": "v2.0.0"},
                            "update": {"median_interval_seconds": 3600},
                            "releases": {
                                "v2.0.0": {"downloaded_assets": ["a.zip"]},
                                "v1.0.0": {"downloaded_assets": []},
                            },
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

        svc = _service()
        items = svc.list_repo_summaries(config=cfg, next_runs={}, scheduler_enabled=False)

        by_key = {item["key"]: item for item in items}
        assert by_key["owner/repo"]["downloaded_releases_total"] == 1
        assert by_key["owner/repo"]["recommended_interval_seconds"] == 123
        assert by_key["owner/another"]["downloaded_releases_total"] == 0

        one = svc.get_repo_summary(config=cfg, repo_key="owner/repo", next_run_at=None)
        assert one["key"] == "owner/repo"
        assert one["downloaded_releases_total"] == 1
        assert one["recommended_interval_seconds"] == 123


def test_get_repo_summary_raises_for_unknown_repo() -> None:
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        cfg = _write_config(base)
        svc = _service()

        with pytest.raises(ValueError, match="unknown repo"):
            svc.get_repo_summary(config=cfg, repo_key="owner/missing", next_run_at=None)


def test_get_repo_activity_and_releases_are_filtered_and_sorted() -> None:
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        cfg = _write_config(base)
        cfg.state_file.write_text(
            json.dumps(
                {
                    "version": 1,
                    "repos": {
                        "owner/repo": {
                            "activity": [
                                {"time": "2026-01-01T00:00:00+00:00", "type": "check"},
                                {"time": "2026-01-02T00:00:00+00:00", "type": "download"},
                                "bad-item",
                            ],
                            "releases": {
                                "v1.0.0": {"published_at": "2026-01-01T00:00:00+00:00", "downloaded_assets": ["a"]},
                                "v2.0.0": {"published_at": "2026-02-01T00:00:00+00:00", "downloaded_assets": ["b", "c"]},
                            },
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

        svc = _service()
        activity = svc.get_repo_activity(config=cfg, repo_key="owner/repo", limit=2)
        assert len(activity) == 1
        assert activity[0]["type"] == "download"

        releases = svc.get_repo_releases(config=cfg, repo_key="owner/repo", limit=10)
        assert [item["tag"] for item in releases] == ["v2.0.0", "v1.0.0"]
        assert releases[0]["downloaded_assets_count"] == 2
