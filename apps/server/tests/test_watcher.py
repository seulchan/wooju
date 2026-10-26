"""Tests for the debounced Brain watcher (app.watcher).

Two angles:
  - a fast, deterministic restart-on-error test using a fake ``awatch``;
  - a real-filesystem integration test that a written/deleted note becomes visible.
"""

from __future__ import annotations

import asyncio
import contextlib

from watchfiles import awatch  # noqa: F401  (asserts the dependency is importable)

from app import watcher as watcher_module
from app.config import watch_enabled
from brain_core.index import BrainIndex


def _run(coro):
    return asyncio.run(coro)


def test_watch_enabled_flag(monkeypatch):
    monkeypatch.delenv("WOOJU_DISABLE_FILE_WATCH", raising=False)
    assert watch_enabled() is True
    for val in ("1", "true", "yes", "on", "TRUE"):
        monkeypatch.setenv("WOOJU_DISABLE_FILE_WATCH", val)
        assert watch_enabled() is False
    for val in ("", "0", "false", "no", "off"):
        monkeypatch.setenv("WOOJU_DISABLE_FILE_WATCH", val)
        assert watch_enabled() is True


def test_watcher_restarts_after_error_then_rescans(monkeypatch, make_brain):
    """A watcher error (e.g. Brain dir removed) must not crash the loop."""
    brain = make_brain({"wiki/a.md": "# A"})
    idx = BrainIndex()
    idx.scan(brain)

    state = {"calls": 0}

    async def fake_awatch(root, **kwargs):
        state["calls"] += 1
        if state["calls"] == 1:
            raise OSError("directory vanished")
        # Second arm yields one batch, then blocks until cancelled (like awatch).
        yield {("modified", str(brain / "wiki" / "b.md"))}
        await asyncio.Event().wait()

    monkeypatch.setattr(watcher_module, "awatch", fake_awatch)

    async def scenario():
        (brain / "wiki" / "b.md").write_text("# B")  # the change the batch reports
        task = asyncio.create_task(
            watcher_module.watch_and_refresh(
                idx, brain, debounce_seconds=0.001, backoff_seconds=0.001
            )
        )
        try:
            for _ in range(200):
                await asyncio.sleep(0.005)
                if idx.get("wiki/b") is not None:
                    break
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    _run(scenario())
    assert state["calls"] >= 2  # the loop re-armed after the error
    assert idx.get("wiki/b") is not None  # rescan after restart saw the new file


def test_watcher_rescans_on_real_filesystem(make_brain):
    """A note written/deleted externally becomes visible after a debounced rescan.

    Native filesystem event latency (FSEvents on macOS, inotify on Linux) varies,
    so this polls generously. It is the one test that exercises real watchfiles.
    """
    brain = make_brain({"wiki/a.md": "# A"})
    idx = BrainIndex()
    idx.scan(brain)
    assert idx.get("wiki/b") is None
    original_indexed_at = idx.indexed_at

    async def scenario():
        task = asyncio.create_task(
            watcher_module.watch_and_refresh(
                idx, brain, debounce_seconds=0.05, backoff_seconds=0.05
            )
        )
        try:
            await asyncio.sleep(0.2)  # let the watch arm
            (brain / "wiki" / "b.md").write_text("# B added")
            (brain / "wiki" / "a.md").write_text("# A changed")
            for _ in range(160):  # up to ~8s for sluggish event backends
                await asyncio.sleep(0.05)
                b = idx.get("wiki/b")
                a = idx.get("wiki/a")
                if b is not None and a is not None and a.title == "A changed":
                    break
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    _run(scenario())
    assert idx.get("wiki/b") is not None
    assert idx.get("wiki/a").title == "A changed"
    assert idx.indexed_at != original_indexed_at  # indexed_at advanced on rescan
