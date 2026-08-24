"""Security policy contracts that exercise repository behavior."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _is_git_ignored(path: str) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", "--quiet", "--no-index", path],
        cwd=PROJECT_ROOT,
        check=False,
    )
    return result.returncode == 0


@pytest.mark.parametrize("path", [".env", ".env.local", ".env.production"])
def test_local_dotenv_files_are_ignored(path: str) -> None:
    """Catch accidental commits of common local dotenv variants."""
    assert _is_git_ignored(path)


def test_example_dotenv_remains_trackable() -> None:
    """Keep the placeholder-only configuration example available to users."""
    assert not _is_git_ignored(".env.example")
