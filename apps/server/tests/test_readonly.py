"""Read-only invariant regression tests.

The Brain filesystem is the single source of truth; the API only reads it.
These tests assert that scanning, rescanning, and watcher-driven refresh never:
  - change file *contents*,
  - change file *mtimes*,
  - create, delete, rename, or move any file (no hidden index inside the Brain).
"""

from __future__ import annotations

import asyncio
import contextlib
import os
from pathlib import Path

from app import watcher as watcher_module
from brain_core.index import BrainIndex

FILES = {
    "wiki/concepts/a.md": "---\ntitle: A\ntype: concept\n---\nBody A.\n",
    "wiki/insights/p.md": (
        "---\norigin: synthesis\nstatus: provisional\ninsight_kind: pattern\n"
        'derived_from: ["[[concepts/a]]"]\n---\nDerived.\n'
    ),
    "sources/s.md": "---\nsource_type: paper\nstatus: active\n---\nSource.\n",
    "memory/m.md": "# Memory note",
}


def _fingerprint(root: Path) -> tuple[dict[str, bytes], dict[str, float], frozenset[str]]:
    """Capture (relpath -> bytes, relpath -> mtime, all-relative-paths)."""
    contents: dict[str, bytes] = {}
    mtimes: dict[str, float] = {}
    paths: set[str] = set()
    for path in sorted(root.rglob("*")):
        if path.is_dir():
            continue
        rel = path.relative_to(root).as_posix()
        paths.add(rel)
        if not path.is_symlink():
            contents[rel] = path.read_bytes()
            mtimes[rel] = path.stat().st_mtime_ns
    return contents, mtimes, frozenset(paths)


def test_scan_does_not_mutate_brain(make_brain):
    brain = make_brain(FILES)
    before = _fingerprint(brain)

    idx = BrainIndex()
    idx.scan(brain)
    idx.scan(brain)  # a second scan must also be a no-op on disk

    after = _fingerprint(brain)
    assert after == before


def test_no_hidden_index_created_in_brain(make_brain):
    """No second knowledge database: scanning writes nothing inside the Brain."""
    brain = make_brain(FILES)
    before = _fingerprint(brain)

    BrainIndex().scan(brain)

    after = _fingerprint(brain)
    assert after[2] == before[2]  # no new files (no index/cache/db artifact)
    # Nothing that looks like a hidden index/cache sneaks in.
    assert not any(
        rel.startswith(".") or rel.endswith((".sqlite", ".db", ".index", ".cache"))
        for rel in after[2]
    )


def test_watcher_rescan_does_not_mutate_brain(make_brain, monkeypatch):
    """A watcher-driven refresh rescans in place and never touches the Brain."""
    brain = make_brain(FILES)
    # Hold mtimes fixed so any spurious write would be obvious.
    fixed = {rel: 1_000_000 for rel in FILES}
    for rel, ts in fixed.items():
        os.utime(brain / rel, (ts, ts))
    before = _fingerprint(brain)

    idx = BrainIndex()
    idx.scan(brain)

    async def fake_awatch(root, **kwargs):
        yield {("modified", str(brain / "wiki" / "concepts" / "a.md"))}
        await asyncio.Event().wait()

    monkeypatch.setattr(watcher_module, "awatch", fake_awatch)

    async def scenario():
        task = asyncio.create_task(
            watcher_module.watch_and_refresh(
                idx, brain, debounce_seconds=0.001, backoff_seconds=0.001
            )
        )
        try:
            for _ in range(100):
                await asyncio.sleep(0.005)
                if idx.indexed_at is not None:
                    break
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    asyncio.run(scenario())
    assert _fingerprint(brain) == before  # contents, mtimes, file list unchanged
