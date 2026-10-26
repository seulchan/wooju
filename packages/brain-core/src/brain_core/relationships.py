"""Pure in-memory resolution of explicit Brain relationships.

Parsing and filesystem access happen elsewhere. This module only resolves the
references already present on normalized records and preserves unresolved
references exactly as the Brain supplied them.
"""

from __future__ import annotations

from collections.abc import Mapping

from .markdown import normalize_target
from .records import Record, ResolvedRef


def resolve_relationships(records: Mapping[str, Record]) -> None:
    """Resolve wikilinks and ``derived_from`` refs against ``records`` in place.

    Records are built in a private mapping before this function runs, so the
    catalog can publish the fully resolved mapping in one assignment. No
    relationship is inferred: an unmatched reference remains unresolved.
    """
    for record in records.values():
        for link in record.links:
            link.resolved_id = resolve_target(link.target, records)
        record.derived_from_resolved = [
            _resolve_derived_ref(reference, records) for reference in record.derived_from
        ]


def resolve_target(target: str | None, records: Mapping[str, Record]) -> str | None:
    """Resolve a target to an id using exact or deterministic suffix matching."""
    normalized = normalize_target(target)
    if not normalized:
        return None
    if normalized in records:
        return normalized

    suffix = "/" + normalized
    candidates = [record_id for record_id in records if record_id.endswith(suffix)]
    if not candidates:
        return None
    return min(candidates, key=lambda record_id: (record_id.count("/"), record_id))


def _resolve_derived_ref(reference: str, records: Mapping[str, Record]) -> ResolvedRef:
    """Resolve one raw derivation ref while retaining its original spelling."""
    resolved_id = resolve_target(normalize_target(reference), records)
    return ResolvedRef(
        ref=reference,
        resolved_id=resolved_id,
        title=records[resolved_id].title if resolved_id is not None else None,
    )
