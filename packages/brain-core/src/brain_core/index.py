"""Deterministic in-memory catalog of normalized Brain records.

Filesystem ingestion is delegated to :mod:`brain_core.reader`, and explicit
relationship resolution is delegated to :mod:`brain_core.relationships`. The catalog
owns publication and querying of the resulting read-only projection; the
filesystem remains the single canonical source and no index is written to disk.
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any

from .reader import read_records
from .records import Record
from .relationships import resolve_relationships

logger = logging.getLogger("brain_core")

# Search ranking constants (higher = better match location).
_SCORE_TITLE = 100
_SCORE_ALIAS = 60
_SCORE_BODY = 10
_SCORE_META = 1


class BrainIndex:
    """An in-memory catalog published atomically after each complete scan."""

    def __init__(self) -> None:
        self._records: dict[str, Record] = {}
        # ISO-8601 UTC of the most recent scan; bumped on every (re)scan so a
        # frontend can detect that the index has changed without a restart.
        self.indexed_at: str | None = None

    @property
    def records(self) -> Mapping[str, Record]:
        """Published records as a read-only mapping for diagnostic consumers.

        Query and projection code should prefer the catalog methods below. The
        mapping remains available for inspection and compatibility, but callers
        cannot replace or add records outside a scan publication.
        """
        return MappingProxyType(self._records)

    # ------------------------------------------------------------------ scan

    def scan(self, root: Path) -> None:
        """Read and index every ``.md`` file under ``root``.

        One unreadable/malformed note is logged and skipped; it never aborts the
        scan. Symlinks (files or directories) are never followed, so the index
        can't escape ``root``. Hidden directories (``.git``, ``.obsidian``,
        ``.agents``, ``.claude``, …) are pruned — they are tooling/config, not
        Brain content. Notes are ingested into a fresh dict, links/derivation
        refs resolved against it, and the result is published in one atomic
        assignment so a concurrent API request never observes a half-built index.
        After publishing, ``indexed_at`` is stamped.
        """
        built = read_records(root)
        resolve_relationships(built)

        # Publish only after ingestion and resolution are complete. Requests
        # therefore see either the previous snapshot or this whole snapshot,
        # never a half-built catalog.
        self._records = built
        self.indexed_at = datetime.now(UTC).isoformat()
        logger.info("Indexed %d notes under %s", len(self._records), root)

    # ------------------------------------------------------------------ query

    def get(self, record_id: str) -> Record | None:
        """Dict-only lookup. Performs no filesystem access (path-traversal-safe)."""
        return self._records.get(record_id)

    def all_records(self) -> tuple[Record, ...]:
        """Return the current snapshot for read-only projection consumers."""
        return tuple(self._records.values())

    def knowledge(self, subtype: str | None = None) -> list[Record]:
        recs = [r for r in self._records.values() if r.category == "knowledge"]
        return self._filter_sort(recs, subtype=subtype)

    def insights(self, status: str | None = None, kind: str | None = None) -> list[Record]:
        recs = [r for r in self._records.values() if r.category == "insight"]
        return self._filter_sort(recs, status=status, kind=kind)

    def sources(self) -> list[Record]:
        return self._sorted_path([r for r in self._records.values() if r.category == "source"])

    def recent(self, limit: int = 20) -> list[Record]:
        limit = _clamp(limit, 1, 100, default=20)
        # Stable sort: path asc, then modified_at desc → modified desc with path tiebreak.
        ordered = self._sorted_path(list(self._records.values()))
        ordered.sort(key=lambda r: r.modified_at or "", reverse=True)
        return ordered[:limit]

    def stats(self) -> dict[str, Any]:
        records = list(self._records.values())
        by_category = Counter(r.category for r in records)
        by_subtype = Counter(r.subtype for r in records if r.subtype)
        by_status = Counter(r.status for r in records if r.status)
        modified = sorted(r.modified_at for r in records if r.modified_at)
        return {
            "total": len(records),
            "by_category": dict(sorted(by_category.items())),
            "by_subtype": dict(sorted(by_subtype.items())),
            "by_status": dict(sorted(by_status.items())),
            "modified_range": {
                "earliest": modified[0] if modified else None,
                "latest": modified[-1] if modified else None,
            },
            "indexed_at": self.indexed_at,
        }

    def overview(self) -> dict[str, Any]:
        """Current Brain totals for the Home overview (deterministic, no scores)."""
        records = list(self._records.values())
        by_cat = Counter(r.category for r in records)
        provisional = sum(
            1 for r in records if r.category == "insight" and r.status == "provisional"
        )
        return {
            "knowledge": by_cat.get("knowledge", 0),
            "insight": by_cat.get("insight", 0),
            "source": by_cat.get("source", 0),
            "provisional_insights": provisional,
            "total": len(records),
            "main_areas": self._main_areas(records),
            "indexed_at": self.indexed_at,
        }

    @staticmethod
    def _main_areas(records: list[Record]) -> list[dict[str, Any]]:
        """Deterministic major knowledge areas, grounded in the Brain's documented
        ``wiki/`` subdirectory taxonomy (concepts, overviews, how-tos, questions,
        mental-models — see ``docs/KNOWLEDGE.md``).

        Each area = the wiki subdirectory a knowledge note lives under, counted
        and title-cased. Not LLM clustering, not invented categories. Capped to
        the 4 largest areas and returned only when at least two exist (a
        single-area Brain gains nothing from a "Main areas" line). Sort is
        count desc → label asc for stable output.
        """
        counts: Counter[str] = Counter()
        for r in records:
            if r.category != "knowledge" or not r.path.startswith("wiki/"):
                continue
            parts = r.path.split("/")
            # parts[0] == "wiki"; parts[1] is the knowledge subdirectory.
            if len(parts) < 3:
                continue
            counts[parts[1]] += 1
        if len(counts) < 2:
            return []
        ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:4]
        return [{"label": _titlecase_slug(label), "count": count} for label, count in ordered]

    def changes(self, since: str | None = None) -> list[Record]:
        """Records whose ``modified_at`` falls at/after ``since`` (newest first).

        ``since=None`` returns every record that has a known modification time.
        ISO timestamps are parsed and compared as datetimes so timezone-aware
        values compare correctly (they are all UTC in this codebase). Records
        without a ``modified_at`` are excluded when a window is requested.
        """
        records = list(self._records.values())
        since_dt = _parse_iso(since)
        if since_dt is not None or since is not None:
            records = [
                r
                for r in records
                if r.modified_at
                and (since_dt is None or ((_parse_iso(r.modified_at) or datetime.max) >= since_dt))
            ]
        ordered = self._sorted_path(records)
        ordered.sort(key=lambda r: r.modified_at or "", reverse=True)
        return ordered

    def search(
        self,
        query: str,
        *,
        category: str | None = None,
        subtype: str | None = None,
        status: str | None = None,
        kind: str | None = None,
        limit: int = 50,
    ) -> list[tuple[int, Record]]:
        """Deterministic full-text search. Returns ``(score, record)`` ranked.

        Substring matching (language-agnostic, CJK-safe). All whitespace-split
        terms must appear in the note's haystack (title + aliases + body + textual
        frontmatter). An empty query yields no hits. Ranking: title > alias >
        body > metadata, then modified_at desc, then path asc.
        """
        limit = _clamp(limit, 1, 200, default=50)
        terms = [term for term in (query or "").lower().split() if term]
        if not terms:
            return []

        scored: list[tuple[int, Record]] = []
        for record in self._records.values():
            if category and record.category != category:
                continue
            if subtype and record.subtype != subtype:
                continue
            if status and record.status != status:
                continue
            if kind and record.kind != kind:
                continue
            haystack = self._haystack(record)
            if not all(term in haystack for term in terms):
                continue
            scored.append((self._score(record, terms), record))

        # Stable ranking: path asc → modified desc → score desc.
        scored.sort(key=lambda sr: sr[1].path)
        scored.sort(key=lambda sr: sr[1].modified_at or "", reverse=True)
        scored.sort(key=lambda sr: sr[0], reverse=True)
        return scored[:limit]

    # -------------------------------------------------------------- internals

    @staticmethod
    def _haystack(record: Record) -> str:
        parts: list[str] = [record.title, *record.aliases, record.content]
        for value in record.metadata.values():
            if isinstance(value, str):
                parts.append(value)
            elif isinstance(value, list):
                parts.extend(str(item) for item in value)
            else:
                parts.append(str(value))
        return "\n".join(parts).lower()

    @staticmethod
    def _score(record: Record, terms: list[str]) -> int:
        title_lower = record.title.lower()
        alias_lower = [a.lower() for a in record.aliases]
        body_lower = record.content.lower()
        total = 0
        for term in terms:
            if term in title_lower:
                total += _SCORE_TITLE
            elif any(term in alias for alias in alias_lower):
                total += _SCORE_ALIAS
            elif term in body_lower:
                total += _SCORE_BODY
            else:
                total += _SCORE_META  # matched only in frontmatter text
        return total

    @staticmethod
    def _sorted_path(records: list[Record]) -> list[Record]:
        return sorted(records, key=lambda r: r.path)

    def _filter_sort(
        self,
        records: list[Record],
        *,
        subtype: str | None = None,
        status: str | None = None,
        kind: str | None = None,
    ) -> list[Record]:
        filtered = records
        if subtype is not None:
            filtered = [r for r in filtered if r.subtype == subtype]
        if status is not None:
            filtered = [r for r in filtered if r.status == status]
        if kind is not None:
            filtered = [r for r in filtered if r.kind == kind]
        return self._sorted_path(filtered)


def _clamp(value: Any, low: int, high: int, *, default: int) -> int:
    try:
        ivalue = int(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, ivalue))


def _parse_iso(value: str | None) -> datetime | None:
    """Parse an ISO-8601 timestamp (lenient about ``Z``), or ``None`` if invalid/absent."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


_AREA_LABELS = {
    "concepts": "Concepts",
    "overviews": "Overviews",
    "questions": "Questions",
    "how-tos": "How-tos",
    "mental-models": "Mental models",
}


def _titlecase_slug(slug: str) -> str:
    """Display label for a wiki folder: ``mental-models`` → ``Mental models``."""
    if slug in _AREA_LABELS:
        return _AREA_LABELS[slug]
    words = [w for w in slug.replace("_", "-").split("-") if w]
    return " ".join(words).capitalize()
