from __future__ import annotations

from pathlib import Path


def test_ci_workflow_exists() -> None:
    assert Path(".github/workflows/ci.yml").exists()
