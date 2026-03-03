from __future__ import annotations

from pathlib import Path


def test_vercel_proxy_targets_v2_only() -> None:
    proxy = Path("deploy/vercel/api/v2/[...path].js").read_text(encoding="utf-8")
    assert "/api/v2" in proxy
    assert "/api/v1" not in proxy
