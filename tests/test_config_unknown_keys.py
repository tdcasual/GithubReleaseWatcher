from __future__ import annotations

import tempfile
from pathlib import Path

from github_release_watcher.config import load_config


def test_load_config_warns_unknown_top_level_keys(caplog) -> None:
    with tempfile.TemporaryDirectory() as td:
        cfg_path = Path(td) / "config.toml"
        cfg_path.write_text(
            "\n".join(
                [
                    "interval_seconds = 60",
                    'download_dir = "./downloads"',
                    'state_file = "./state.json"',
                    "keep_last = 1",
                    'unexpected_field = "value"',
                    "",
                    "[[repos]]",
                    'name = "owner/repo"',
                    "",
                ]
            ),
            encoding="utf-8",
        )

        load_config(cfg_path)
        assert "unknown config key ignored" in caplog.text.lower()
