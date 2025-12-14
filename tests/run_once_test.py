#!/usr/bin/env python3
from __future__ import annotations

import logging
import sys
from pathlib import Path
import json
import argparse

# Ensure project root is on sys.path so local package imports work when running this script
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from github_release_watcher import watcher
from github_release_watcher.config import load_config


class FakeDownloader:
    def __init__(self, github_token: str | None = None, timeout_seconds: int = 60, max_retries: int = 3):
        self.github_token = github_token

    def download_release_asset(self, repo_url: str, tag: str, asset, dest_dir: Path) -> None:
        dest_dir.mkdir(parents=True, exist_ok=True)
        path = dest_dir / asset.name
        path.write_text(f"fake-content for {asset.name}\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fake", action="store_true", help="Use FakeDownloader (writes simulated files, no network).")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config(Path("config.toml"))

    if args.fake:
        # Replace real downloader with fake one (no network download).
        watcher.GitHubReleaseAssetDownloader = FakeDownloader

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
