"""Shared test fixtures and helpers.

Every Brain used in tests is a synthetic, temporary fixture under ``tmp_path`` —
the reader is never pointed at a real Brain. Helpers here also back the read-only
invariant: snapshots let tests prove the Brain is never modified by the API.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# The server answers only requests addressed to this Mac (127.0.0.1/localhost).
# TestClient's default base URL is http://testserver, so tests speak as localhost.
TestClient.__init__.__defaults__ = tuple(
    "http://localhost" if d == "http://testserver" else d for d in TestClient.__init__.__defaults__
)


@pytest.fixture(autouse=True)
def _disable_file_watch(monkeypatch):
    """Disable the live filesystem watcher for every test by default.

    The watcher is exercised directly in ``test_watcher.py``. Keeping it off here
    means the API/health/index tests stay fast and deterministic — no watchfiles
    background thread is spawned per ``TestClient``. The app stays read-only
    either way; this only switches the auto-refresh off.
    """
    monkeypatch.setenv("WOOJU_DISABLE_FILE_WATCH", "1")


@pytest.fixture(autouse=True)
def _isolate_app_data(monkeypatch, tmp_path):
    """Keep settings and proposals in a temp folder, never in ~/.wooju."""
    monkeypatch.setenv("WOOJU_DATA_DIR", str(tmp_path / "app-data"))


@pytest.fixture(autouse=True)
def _isolate_ui_state(monkeypatch, tmp_path):
    """Point the UI-state file at a temp path so tests never touch ~/.wooju-brain-ui.

    ``WOOJU_UI_STATE_PATH`` redirects ``app.ui_state.state_file()`` outside the
    real home directory; this both isolates tests and keeps them deterministic.
    """
    monkeypatch.setenv("WOOJU_UI_STATE_PATH", str(tmp_path / "ui-state" / "state.json"))


@pytest.fixture
def make_brain(tmp_path: Path):
    """Return a factory ``make_brain(files, mtimes=None) -> Path``.

     ``files`` maps a relative path to file content; parent dirs are created.
     ``mtimes`` optionally sets each file's mtime (epoch seconds) for deterministic
     ordering. Each call builds a fresh subdirectory so a test can build several
    Brains without colliding.
    """
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
                path = root / rel
                os.utime(path, (ts, ts))
        return root

    return _make


@pytest.fixture
def snapshot():
    """Return a function mapping a Brain root to ``{relpath: bytes}`` for all real files.

    Used to assert the Brain is byte-for-byte unchanged before/after API calls.
    """

    def _snap(root: Path) -> dict[str, bytes]:
        out: dict[str, bytes] = {}
        for path in sorted(root.rglob("*")):
            if path.is_file() and not path.is_symlink():
                out[path.relative_to(root).as_posix()] = path.read_bytes()
        return out

    return _snap
