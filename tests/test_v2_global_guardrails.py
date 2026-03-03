from __future__ import annotations

from pathlib import Path


def test_repo_disallows_api_v1_and_window_grw_strings() -> None:
    roots = [Path("github_release_watcher"), Path("deploy"), Path("README.md")]
    banned = ["/api/v1", "window.GRW"]
    hits: list[tuple[str, str]] = []
    for root in roots:
        files = [root] if root.is_file() else [p for p in root.rglob("*") if p.is_file()]
        for file in files:
            text = file.read_text(encoding="utf-8", errors="ignore")
            for token in banned:
                if token in text:
                    hits.append((str(file), token))
    assert not hits
