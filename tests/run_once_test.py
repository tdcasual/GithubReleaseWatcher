#!/usr/bin/env python3
from __future__ import annotations

import logging
import sys
from pathlib import Path
import json

# Ensure project root is on sys.path so local package imports work when running this script
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from github_release_watcher import watcher
from github_release_watcher.config import load_config


class FakeDownloader:
    def __init__(self, fetch_path: str = "fetch", github_token: str | None = None):
        self.fetch_path = fetch_path
        self.github_token = github_token

    def download_release_asset(self, repo_url: str, tag: str, asset_name: str, dest_dir: Path) -> None:
        dest_dir.mkdir(parents=True, exist_ok=True)
        path = dest_dir / asset_name
        path.write_text(f"fake-content for {asset_name}\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config(Path("config.toml"))

    # Replace real downloader with fake one to avoid needing 'fetch'
    watcher.FetchDownloader = FakeDownloader

    rc = watcher.run_once(cfg)

    print("\n=== Test summary ===")
    download_root = cfg.download_dir
    print(f"Download root: {download_root}")
    for p in sorted(download_root.rglob("*")):
        print(p)

    state_path = cfg.state_file
    if state_path.exists():
        try:
            print("\nState file:")
            print(state_path.read_text(encoding="utf-8"))
        except Exception as exc:
            print("Failed reading state:", exc)
    else:
        print("No state file created.")

    return rc


if __name__ == "__main__":
    sys.exit(main())
