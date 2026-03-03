from __future__ import annotations

from pathlib import Path


def test_no_manual_static_sync_script() -> None:
    assert not Path("scripts/release/sync_vercel_public.sh").exists()


def test_vercel_public_contains_built_index() -> None:
    assert Path("deploy/vercel/public/index.html").exists()
