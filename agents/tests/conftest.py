"""Shared fixtures for brain-core tests. Every Brain is a temporary fixture."""

from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture
def make_brain(tmp_path: Path):
    """Return ``make_brain(files, mtimes=None) -> Path`` that builds a fresh Brain."""
    counter = 0

    def _make(files: dict[str, str], mtimes: dict[str, int] | None = None) -> Path:
        nonlocal counter
        counter += 1
        root = tmp_path / f"brain-{counter}"
        root.mkdir()
        for rel, content in files.items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        if mtimes:
            for rel, ts in mtimes.items():
                os.utime(root / rel, (ts, ts))
        return root

    return _make
