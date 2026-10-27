"""Debounced filesystem watcher that rescans the Brain index on change.

This keeps the in-memory index a faithful, eventually-current projection of the
Brain filesystem while another process (Codex, Claude Code, an editor) edits the
Markdown. It is strictly **read-only**: it only *observes* the filesystem and
asks the index to re-read. It never creates, writes, moves, deletes, or touches
the mtime of any Brain file (Invariant 4), and it writes nothing to disk (no
hidden index files — there is no second knowledge database).

Flow::

    Brain file change (watchfiles)
      ↓
    debounced refresh/rescan (coalesce a burst into one ``index.scan``)
      ↓
    in-memory index updated + ``indexed_at`` stamped
      ↓
    subsequent API requests see the current state

If the watch fails — most importantly when the Brain directory is removed while
the API is running — the loop backs off and retries, so a transiently missing
Brain never crashes the API and a recreated Brain is picked back up.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from watchfiles import awatch

from brain_core.index import BrainIndex

logger = logging.getLogger("wooju")

# How long to wait after a burst of events before rescanning. ``awatch`` already
# debounces internally; this adds a short coalescing window so a flurry of edits
# by another tool becomes a single rescan.
DEBOUNCE_SECONDS = 0.4
# Wait this long before re-arming the watch after an error (e.g. the Brain dir
# was removed). Keeps the retry cheap rather than spinning.
RESTART_BACKOFF_SECONDS = 2.0


def _is_note_path(root: Path, path: str) -> bool:
    """Ignore hidden folders (history, .obsidian, …): only notes trigger a rescan."""
    try:
        parts = Path(path).relative_to(root).parts
    except ValueError:
        return False
    return not any(part.startswith(".") for part in parts)


async def watch_and_refresh(
    index: BrainIndex,
    root: Path,
    *,
    debounce_seconds: float = DEBOUNCE_SECONDS,
    backoff_seconds: float = RESTART_BACKOFF_SECONDS,
) -> None:
    """Watch ``root`` forever and debounced-rescan ``index`` on any change.

    Runs until the task is cancelled (the API lifespan cancels it on shutdown).
    Any watcher error is logged and the loop retries after ``backoff_seconds``;
    cancellation propagates. Each rescan runs off the event loop (via
    :func:`asyncio.to_thread`) so API requests are not blocked while a large
    Brain re-reads.
    """
    logger.info("Watching Brain for changes: %s", root)
    while True:
        try:
            async for changes in awatch(root, watch_filter=lambda _c, p: _is_note_path(root, p)):
                if not changes:
                    continue
                # Coalesce a burst: wait out the debounce window, then rescan
                # once. ``awatch`` yields a batch per coalesced event set, so a
                # near-simultaneous flurry is typically one batch → one rescan.
                await asyncio.sleep(debounce_seconds)
                await asyncio.to_thread(index.scan, root)
                logger.info("Brain reindexed after %d filesystem change(s)", len(changes))
        except asyncio.CancelledError:
            logger.info("Brain watcher stopped")
            raise
        except Exception as exc:  # noqa: BLE001 — any watcher failure must not crash the API
            logger.warning("Brain watcher interrupted (%s); retrying in %ss", exc, backoff_seconds)
            await asyncio.sleep(backoff_seconds)
