"""Pydantic response models for the Wooju API.

These DTOs shape the HTTP responses. Domain models live in :mod:`brain_core.records`;
mappers here convert a :class:`~brain_core.records.Record` into the lighter summary
shapes used by list/search endpoints, while ``GET /api/records/{id}`` returns the
full :class:`Record` directly.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from brain_core.records import Category, Record

HealthStatus = Literal["ok", "misconfigured"]


class HealthResponse(BaseModel):
    """Result of GET /api/health — API status plus Brain configuration status."""

    status: HealthStatus
    api: Literal["ok"]
    brain_path: str | None
    brain_configured: bool
    brain_exists: bool
    brain_is_directory: bool
    brain_valid: bool
    message: str
    indexed_at: str | None = None  # last in-memory (re)scan time; advances on watcher refresh


class RecordSummary(BaseModel):
    """Lightweight record view for list endpoints."""

    id: str
    path: str
    title: str
    category: Category
    subtype: str | None = None
    status: str | None = None
    kind: str | None = None
    modified_at: str | None = None
    excerpt: str | None = None  # short plain-text preview of the body
    derived_from_count: int = 0  # number of derivation refs (insight provenance)


class ListResponse(BaseModel):
    """Generic list response."""

    total: int
    items: list[RecordSummary]


class SearchHit(BaseModel):
    """A single search match with a relevance score and snippet."""

    id: str
    path: str
    title: str
    category: Category
    subtype: str | None = None
    status: str | None = None  # preserved insight lifecycle status (not surfaced for non-insights)
    kind: str | None = None
    score: int
    snippet: str


class SearchResponse(BaseModel):
    query: str
    total: int
    hits: list[SearchHit]


class RecentResponse(BaseModel):
    total: int
    items: list[RecordSummary]


class StatsResponse(BaseModel):
    """Aggregate counts over the indexed Brain."""

    total: int
    by_category: dict[str, int]
    by_subtype: dict[str, int]
    by_status: dict[str, int]
    modified_range: dict[str, str | None] = Field(default_factory=dict)
    indexed_at: str | None = None


class MainArea(BaseModel):
    """One deterministic knowledge grouping for the Home overview.

    Grounded in the Brain's own documented structure (the ``wiki/`` subdirectory
    taxonomy from ``docs/KNOWLEDGE.md`` / ``docs/OPERATIONS.md``) — never LLM
    clustering or invented categories. ``label`` is display-ready (title-cased).
    """

    label: str
    count: int


class OverviewResponse(BaseModel):
    """Current Brain totals for the Home overview (no synthetic scores)."""

    knowledge: int
    insight: int
    source: int
    provisional_insights: int
    total: int
    # Deterministic major knowledge areas (wiki subdirectories). Empty when the
    # Brain has fewer than two distinct areas, so a single-area Brain stays clean.
    main_areas: list[MainArea] = Field(default_factory=list)
    indexed_at: str | None = None


class ChangeItem(BaseModel):
    """One record that changed within a requested period.

    ``change_type`` is intentionally an extensible vocabulary. Phase 1 only
    emits ``added``/``modified``, derived from the disposable ``known`` UI
    snapshot (see :mod:`app.ui_state`). Later phases may add values such as
    ``connected``/``status_change``/``challenged`` without breaking this shape.
    """

    id: str
    path: str
    title: str
    category: Category
    change_type: Literal["added", "modified"]
    modified_at: str | None = None


class ChangesResponse(BaseModel):
    total: int
    since: str | None = None
    items: list[ChangeItem] = Field(default_factory=list)


class GraphNode(BaseModel):
    """One node in the relationship projection (a Brain record, minimal payload).

    Kept deliberately light — no full Markdown body. ``recent`` reflects whether
    the *record* was modified within the requested ``since`` window (reusing Phase
    1's time-window logic); it is ``None`` when no window was requested. It makes
    no claim about when any relationship was created.
    """

    id: str
    title: str
    category: Category
    subtype: str | None = None
    status: str | None = None  # insight lifecycle status (not surfaced for non-insights)
    modified_at: str | None = None
    recent: bool | None = None


class GraphEdge(BaseModel):
    """One explicit relationship edge.

    ``source`` is the record that declares the relationship, ``target`` the
    resolved record. ``type`` is always an explicit relationship the Brain models:

    - ``wikilink`` — a resolved wikilink in the source body
    - ``derived_from`` — derivation provenance (never relabeled to
      evidence/supports/proves)

    There is deliberately **no** creation timestamp: the index only knows a
    per-file ``modified_at``, not when a relationship was added, so fabricating an
    edge time would be dishonest (see ``GraphMeta.edge_creation_known``).
    """

    source: str
    target: str
    type: Literal["wikilink", "derived_from"]


class GraphMeta(BaseModel):
    """Bounding/mode metadata for a graph projection (readability > completeness)."""

    mode: Literal["overview", "focus"]
    focus: str | None = None
    depth: int | None = None  # hops used in focus mode (None in overview)
    limit: int
    since: str | None = None  # the requested change window (echoed back)
    total_nodes: int  # graph-eligible nodes across the whole Brain
    node_count: int  # nodes actually returned (always <= limit)
    edge_count: int
    # Always False: relationship creation times are not knowable from the index,
    # so edges carry no timestamp and recent-change is surfaced at node level only.
    edge_creation_known: bool


class GraphResponse(BaseModel):
    """UI-oriented relationship projection for the future Brain Map."""

    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    meta: GraphMeta


class UiState(BaseModel):
    """UI-only presentation state, stored *outside* the Brain.

    ``known`` is a disposable, rebuildable snapshot of record ids present at the
    last visit, used to tell newly-created records from modified ones. It is
    never canonical knowledge and never influences the Brain.
    """

    last_seen_at: str | None = None
    known: list[str] = Field(default_factory=list)


class UiStateUpdate(BaseModel):
    last_seen_at: str | None = None
    known: list[str] | None = None


# --- Phase 4: Needs attention -------------------------------------------------


# Attention group keys, in the canonical display order. Each key names a
# distinct, deterministic *reason* an item deserves review. The UI surfaces
# existing Brain uncertainty only — it never invents confidence, quality, or
# conflict (see app.projections.attention).
AttentionGroupKey = Literal[
    "provisional",
    "candidate",
    "open_questions",
    "contested",
    "unresolved_derived_from",
    "unresolved_links",
]


class AttentionItem(BaseModel):
    """One review-worthy item surfaced by the Brain's own metadata/structure.

    ``detail`` carries the grounded reason text — e.g. an unresolved target/ref
    — so the UI can show *why* the item is here without inventing a judgment.
    """

    id: str
    path: str
    title: str
    category: Category
    status: str | None = None  # insight lifecycle status (insights only)
    detail: str | None = None  # grounded reason (e.g. unresolved target), never an inference


class AttentionGroup(BaseModel):
    """One attention category: a stable key, a human label, and its items.

    ``key`` is the stable contract; ``label`` is the display text. Only
    non-empty groups are returned so Home stays uncluttered (no "0 of X" rows).
    ``count`` is the true total found; the ``items`` list may be trimmed for the
    unresolved-relationship groups (so the section stays small/actionable) — UIs
    should show "+(count - len(items)) more" when they differ.
    """

    key: AttentionGroupKey
    label: str
    count: int
    items: list[AttentionItem] = Field(default_factory=list)


class AttentionResponse(BaseModel):
    """Deterministic, read-only review-worthy items for "What needs attention?".

    Period-independent: attention reflects the Brain's *current* uncertainty, not
    only recent changes. ``total`` is the sum of all group counts (attention
    items, not distinct records — an insight may appear under more than one
    reason). No score, no confidence, no invented conflict.
    """

    groups: list[AttentionGroup] = Field(default_factory=list)
    total: int = 0


# ---------------------------------------------------------------- mappers


def to_summary(record: Record) -> RecordSummary:
    return RecordSummary(
        id=record.id,
        path=record.path,
        title=record.title,
        category=record.category,
        subtype=record.subtype,
        status=record.status,
        kind=record.kind,
        modified_at=record.modified_at,
        excerpt=_excerpt(record.content),
        derived_from_count=len(record.derived_from),
    )


def _excerpt(content: str, width: int = 180) -> str | None:
    """Short single-line preview of a note's body, or ``None`` if empty.

    Whitespace is collapsed so the preview reads as one line regardless of the
    source formatting. This is a display-only view; it never alters the note.
    """
    # Headings repeat the title or label sections ("## One-line Summary");
    # a preview reads better from the prose, so skip them.
    lines = [line for line in content.splitlines() if not line.lstrip().startswith("#")]
    flat = " ".join(" ".join(lines).split())
    if not flat:
        flat = " ".join(content.split())
    if not flat:
        return None
    if len(flat) <= width:
        return flat
    return flat[:width].rstrip() + "…"


def to_search_hit(record: Record, score: int, snippet: str) -> SearchHit:
    return SearchHit(
        id=record.id,
        path=record.path,
        title=record.title,
        category=record.category,
        subtype=record.subtype,
        status=record.status,
        kind=record.kind,
        score=score,
        snippet=snippet,
    )


# Re-export Record so endpoints can use it as a response_model without importing
# from two places.
__all__ = [
    "AttentionGroup",
    "AttentionGroupKey",
    "AttentionItem",
    "AttentionResponse",
    "ChangeItem",
    "ChangesResponse",
    "GraphEdge",
    "GraphMeta",
    "GraphNode",
    "GraphResponse",
    "HealthResponse",
    "HealthStatus",
    "ListResponse",
    "MainArea",
    "OverviewResponse",
    "RecentResponse",
    "Record",
    "RecordSummary",
    "SearchHit",
    "SearchResponse",
    "StatsResponse",
    "UiState",
    "UiStateUpdate",
    "to_search_hit",
    "to_summary",
]
