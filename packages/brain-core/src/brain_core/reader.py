"""Read-only filesystem adapter for Brain Markdown records.

This module owns directory traversal and turning one Markdown file into the
normalized :class:`~brain_core.records.Record` model. It deliberately has no index,
API, or watcher concerns; callers receive a fresh in-memory mapping that can be
published atomically by the catalog.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from pathlib import Path

from .markdown import extract_title, extract_wikilinks, first_heading, split_frontmatter
from .records import Link, Record, classify, coerce_list

logger = logging.getLogger("brain_core")


def read_records(root: Path) -> dict[str, Record]:
    """Read every safe, visible Markdown file below ``root``.

    A missing/invalid root produces an empty mapping. Individual unreadable or
    malformed files are skipped so one bad note cannot hide the rest of the
    Brain. Symlinks and hidden directories/files are intentionally excluded.
    The returned mapping is not shared with a previous scan.
    """
    if not root.exists() or not root.is_dir():
        logger.warning("Brain root missing/not a dir during scan: %s", root)
        return {}

    records: dict[str, Record] = {}
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        # Tooling/config directories are not Brain content. Sorting keeps the
        # resulting scan deterministic, which makes resolution and tests stable.
        dirnames[:] = sorted(directory for directory in dirnames if not directory.startswith("."))
        for name in sorted(filenames):
            if name.startswith(".") or not name.endswith(".md"):
                continue
            file_path = Path(dirpath) / name
            if file_path.is_symlink():
                continue
            try:
                record = _read_record(root, file_path)
            except (OSError, UnicodeDecodeError, ValueError) as exc:
                logger.warning("Skipping malformed note %s: %s", file_path, exc)
                continue
            if record is not None:
                records[record.id] = record
    return records


def _read_record(root: Path, file_path: Path) -> Record | None:
    """Normalize one Markdown file without resolving cross-record references."""
    relative_path = file_path.relative_to(root)
    text = file_path.read_text(encoding="utf-8")
    frontmatter, body = split_frontmatter(text)
    title = extract_title(frontmatter, body, file_path.stem)
    # A note may keep a source's original title in frontmatter (for citing)
    # and give itself a heading in the reader's language. Show the heading,
    # and keep the original alongside, so a note never has two titles on screen.
    original_title = None
    heading = first_heading(body)
    if heading and heading != title and frontmatter.get("title"):
        original_title, title = title, heading
    category, subtype, kind, status = classify(relative_path, frontmatter)
    return Record(
        id=relative_path.with_suffix("").as_posix(),
        path=relative_path.as_posix(),
        title=title,
        original_title=original_title,
        category=category,
        subtype=subtype,
        content=body,
        metadata=frontmatter,
        links=[Link(**link) for link in extract_wikilinks(body)],
        modified_at=_modified_at(file_path),
        status=status,
        kind=kind,
        derived_from=coerce_list(frontmatter.get("derived_from")),
        aliases=coerce_list(frontmatter.get("aliases")),
    )


def _modified_at(file_path: Path) -> str | None:
    """Return a file's UTC mtime, or ``None`` if it cannot be read."""
    try:
        timestamp = file_path.stat().st_mtime
    except OSError:
        return None
    return datetime.fromtimestamp(timestamp, tz=UTC).isoformat()
