""""What needs attention?" projection for the Home overview (Phase 4).

Surfaces review-worthy content that the Brain **already represents** by its own
metadata, structure, or resolution state. It deterministically groups existing
uncertainty; it never invents an epistemic judgment.

Grounding (from the Brain's own ``docs/EPISTEMICS.md`` / ``SYNTHESIS.md`` /
``KNOWLEDGE.md``):

- **Provisional / Candidate insights** — an insight's top-level lifecycle
  ``status``. These are the active, not-yet-settled lifecycle states.
  ``established`` is settled (not surfaced); ``rejected`` / ``superseded`` are
  decided historical outcomes (not surfaced).

- **Open questions** — notes the Brain routes to a ``questions/`` directory, or
  that carry an explicit ``subtype``/``type`` of ``question``. This is the
  Brain's documented location/taxonomy for unresolved evidence-seeking items.

- **Explicit challenge/conflict** — a record whose nested ``epistemic.status`` is
  exactly ``contested``. This is the Brain's *only* explicit conflict state.
  Conflict is **never** inferred from wording differences, a single source, an
  old timestamp, or any other proxy.

- **Unresolved relationships** — unresolved ``derived_from`` provenance and
  unresolved wikilinks. These are surfaced only for knowledge-bearing records
  (the Brain's own ``docs/`` meta-documentation uses illustrative wikilinks that
  are not broken knowledge, so ``other``-category records are excluded). Kept
  small and actionable via a per-group cap.

``derived_from`` stays derivation provenance — never relabeled to evidence or
proof. The result is deterministic, read-only, and period-independent: attention
reflects the Brain's *current* uncertainty, not only recent changes.
"""

from __future__ import annotations

from brain_core.index import BrainIndex

from ..api.models import AttentionGroup, AttentionGroupKey, AttentionItem, AttentionResponse

# Canonical display order of attention categories.
_GROUP_ORDER: tuple[AttentionGroupKey, ...] = (
    "provisional",
    "candidate",
    "open_questions",
    "contested",
    "unresolved_derived_from",
    "unresolved_links",
)

# Human labels for each stable group key. The label is always shown in the UI
# (state is never color-only).
_LABELS: dict[AttentionGroupKey, str] = {
    "provisional": "Provisional insights",
    "candidate": "Candidate insights",
    "open_questions": "Open questions",
    "contested": "Contested claims",
    "unresolved_derived_from": "Unresolved derivations",
    "unresolved_links": "Unresolved links",
}

# Cap each unresolved-relationship group so the section stays small/actionable.
# Counts in ``AttentionGroup.count`` still reflect the *total* found; only the
# returned ``items`` list is trimmed (the cap is exposed via the trimmed length).
_MAX_UNRESOLVED_ITEMS = 12


def _item_from(record, *, detail: str | None = None) -> AttentionItem:
    return AttentionItem(
        id=record.id,
        path=record.path,
        title=record.title,
        category=record.category,
        status=record.status,
        detail=detail,
    )


def _epistemic_status(record) -> str | None:
    """The nested rigorous-assessment ``epistemic.status``, when it is a dict.

    Distinct from the top-level lifecycle ``status`` (candidate/provisional/
    established/…). Returns ``None`` when there is no nested ``epistemic`` block.
    """
    epi = record.metadata.get("epistemic")
    if not isinstance(epi, dict):
        return None
    value = epi.get("status")
    if isinstance(value, str) and value.strip():
        return value.strip().lower()
    return None


def _is_question(record) -> bool:
    """A note the Brain routes as an open question.

    Grounded in the Brain's documented conventions: the ``questions/`` directory
    (see ``docs/KNOWLEDGE.md`` — "Unresolved evidence-seeking idea → wiki/questions/")
    or an explicit ``subtype``/``type`` of ``question``.
    """
    if "questions/" in record.path:
        return True
    return (record.subtype or "").strip().lower() == "question"


def _collect(index: BrainIndex) -> dict[str, list[AttentionItem]]:
    """Group every attention item by its stable key, sorted by path (deterministic)."""
    groups: dict[str, list[AttentionItem]] = {key: [] for key in _GROUP_ORDER}

    for record in sorted(index.all_records(), key=lambda r: r.path):
        if record.category == "insight":
            status = (record.status or "").strip().lower() if record.status else None
            if status == "provisional":
                groups["provisional"].append(_item_from(record))
            elif status == "candidate":
                groups["candidate"].append(_item_from(record))
            # established / rejected / superseded are decided — not surfaced.

        if _is_question(record):
            groups["open_questions"].append(_item_from(record))

        if _epistemic_status(record) == "contested":
            groups["contested"].append(_item_from(record))

        # Unresolved derivation provenance — one item per unresolved ref, so each
        # broken provenance link is individually actionable.
        if record.category == "insight":
            for ref in record.derived_from_resolved:
                if ref.resolved_id is None:
                    groups["unresolved_derived_from"].append(
                        _item_from(record, detail=ref.ref)
                    )

        # Unresolved wikilinks — knowledge-bearing records only (category !=
        # "other"); the Brain's docs/ templates are illustrative, not broken
        # knowledge. Dedupe by target within a record.
        if record.category != "other":
            seen_targets: set[str] = set()
            for link in record.links:
                if link.resolved_id is None and link.target not in seen_targets:
                    seen_targets.add(link.target)
                    groups["unresolved_links"].append(
                        _item_from(record, detail=link.target)
                    )

    return groups


def compute_attention(index: BrainIndex) -> AttentionResponse:
    """Build the deterministic, read-only "What needs attention?" projection."""
    collected = _collect(index)

    response_groups: list[AttentionGroup] = []
    total = 0
    for key in _GROUP_ORDER:
        items = collected[key]
        if not items:
            continue
        total += len(items)
        # Unresolved groups can grow large; trim the returned examples while the
        # count still reports the true total found (small + actionable).
        is_unresolved = key in ("unresolved_derived_from", "unresolved_links")
        shown = items[:_MAX_UNRESOLVED_ITEMS] if is_unresolved else items
        response_groups.append(
            AttentionGroup(
                key=key,
                label=_LABELS[key],
                count=len(items),
                items=shown,
            )
        )

    return AttentionResponse(groups=response_groups, total=total)
