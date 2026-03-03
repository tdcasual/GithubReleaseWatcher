from __future__ import annotations

import hashlib
from pathlib import Path


FILES = [
    "index.html",
    "app.js",
    "app-runtime.js",
    "app-ui-utils.js",
    "app-auth.js",
    "styles.css",
    "repo.js",
    "repo.html",
    "favicon.svg",
]


def _sha1(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()


def test_vercel_public_matches_static_bundle() -> None:
    root = Path(__file__).resolve().parents[1]
    static_dir = root / "github_release_watcher" / "static"
    vercel_public_dir = root / "deploy" / "vercel" / "public"

    for name in FILES:
        static_file = static_dir / name
        vercel_file = vercel_public_dir / name
        assert _sha1(static_file) == _sha1(vercel_file), f"{name} is out of sync between static/ and deploy/vercel/public/"
