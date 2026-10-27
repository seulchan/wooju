"""Notes whose grounds changed: the Maintainer's "check this again" signal.

An insight is derived from other notes (``derived_from``) and a knowledge note
links to what it rests on. When one of those changes after the note itself,
the note may no longer hold. Wooju does not rewrite it; it surfaces it, so the
user can challenge it again, edit it, or mark it as checked.

"Changed after" is read from the Brain's history (commit order), so notes
created together never show up, and an edit made outside Wooju counts once
Wooju has recorded it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from brain_core import history
from brain_core.changes import data_dir
from brain_core.index import BrainIndex
from brain_core.records import Record

_CACHE: dict[tuple[str, str | None], dict[str, int]] = {}
DEPENDENT_KINDS = ("insight", "knowledge")


def _changes(brain: Path) -> dict[str, int]:
    key = (str(brain), history.head_id(brain))
    if key not in _CACHE:
        _CACHE.clear()
        _CACHE[key] = history.last_changes(brain)
    return _CACHE[key]


def grounds(record: Record) -> list[str]:
    """Ids of the notes this note rests on."""
    ids = [r.resolved_id for r in record.derived_from_resolved if r.resolved_id]
    if record.category in DEPENDENT_KINDS:
        ids += [link.resolved_id for link in record.links if link.resolved_id]
    return [i for i in dict.fromkeys(ids) if i != record.id]


def dependents(index: BrainIndex, record_id: str) -> list[Record]:
    """Notes that rest on ``record_id``."""
    return sorted(
        (
            r
            for r in index.all_records()
            if r.category in DEPENDENT_KINDS and record_id in grounds(r)
        ),
        key=lambda r: r.path,
    )


# ----------------------------------------------------------- acknowledgements


def _ack_file() -> Path:
    return data_dir() / "checked.json"


def _acks(brain: Path) -> dict[str, int]:
    try:
        data = json.loads(_ack_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    value = data.get(str(brain), {})
    return value if isinstance(value, dict) else {}


def is_acknowledged(brain: Path, key: str) -> bool:
    return key in _acks(brain)


def acknowledge(brain: Path, record_id: str) -> None:
    """The user checked this note against its changed grounds."""
    path = _ack_file()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    newest = max(_changes(brain).values(), default=0)
    data.setdefault(str(brain), {})[record_id] = newest
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def changed_grounds(index: BrainIndex, brain: Path) -> list[tuple[Record, Record]]:
    """``(note, ground that changed after it)`` for notes to check again."""
    changes = _changes(brain)
    if not changes:
        return []
    acks = _acks(brain)
    out: list[tuple[Record, Record]] = []
    for record in sorted(index.all_records(), key=lambda r: r.path):
        if record.category not in DEPENDENT_KINDS:
            continue
        own = max(changes.get(record.path, 0), acks.get(record.id, 0))
        newest: tuple[int, Record] | None = None
        for ground_id in grounds(record):
            ground = index.get(ground_id)
            if ground is None:
                continue
            when = changes.get(ground.path, 0)
            if when > own and (newest is None or when > newest[0]):
                newest = (when, ground)
        if newest is not None:
            out.append((record, newest[1]))
    return out


def summary(record: Record) -> dict[str, Any]:
    return {"id": record.id, "title": record.title, "category": record.category}
