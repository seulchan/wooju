"""HTTP routes for the read-only Brain API.

Route functions validate transport inputs and delegate to the catalog or a
projection module. Application startup, file watching, and configuration live
in :mod:`app.main`; filesystem reading and domain resolution live below the
catalog boundary.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from brain_core.markdown import make_snippet
from brain_core.records import Record

from .. import ui_state
from ..config import build_health
from ..projections.attention import compute_attention
from ..projections.graph import project_graph
from .dependencies import BrainPathDep, IndexDep
from .models import (
    AttentionResponse,
    ChangeItem,
    ChangesResponse,
    GraphResponse,
    HealthResponse,
    ListResponse,
    OverviewResponse,
    RecentResponse,
    SearchResponse,
    StatsResponse,
    UiState,
    UiStateUpdate,
    to_search_hit,
    to_summary,
)

api_router = APIRouter(prefix="/api")


@api_router.get("/health", tags=["system"], response_model=HealthResponse)
def health(brain_path: BrainPathDep, index: IndexDep) -> HealthResponse:
    """Report API health, Brain configuration, and catalog freshness."""
    response = build_health(brain_path)
    response.indexed_at = index.indexed_at
    return response


@api_router.get("/stats", tags=["brain"], response_model=StatsResponse)
def stats(index: IndexDep) -> StatsResponse:
    """Aggregate counts by category, subtype, and insight lifecycle status."""
    return StatsResponse(**index.stats())


@api_router.get("/knowledge", tags=["brain"], response_model=ListResponse)
def knowledge(
    index: IndexDep,
    subtype: Annotated[str | None, Query(description="Filter by knowledge subtype")] = None,
) -> ListResponse:
    """Knowledge notes, optionally filtered by subtype."""
    items = [to_summary(record) for record in index.knowledge(subtype)]
    return ListResponse(total=len(items), items=items)


@api_router.get("/insights", tags=["brain"], response_model=ListResponse)
def insights(
    index: IndexDep,
    status: Annotated[str | None, Query(description="Filter by insight status")] = None,
    kind: Annotated[str | None, Query(description="Filter by insight kind")] = None,
) -> ListResponse:
    """Derived insights, optionally filtered by lifecycle status and kind."""
    items = [to_summary(record) for record in index.insights(status, kind)]
    return ListResponse(total=len(items), items=items)


@api_router.get("/sources", tags=["brain"], response_model=ListResponse)
def sources(index: IndexDep) -> ListResponse:
    """Source notes from the Brain's ``sources/`` and ``library/`` areas."""
    items = [to_summary(record) for record in index.sources()]
    return ListResponse(total=len(items), items=items)


@api_router.get("/records/{record_id:path}", tags=["brain"], response_model=Record)
def get_record(record_id: str, index: IndexDep) -> Record:
    """Fetch a record by catalog id without touching the filesystem."""
    if _looks_invalid_id(record_id):
        raise _record_not_found()
    record = index.get(record_id)
    if record is None:
        raise _record_not_found()
    return record


@api_router.get("/search", tags=["brain"], response_model=SearchResponse)
def search(
    index: IndexDep,
    q: Annotated[str, Query(description="Full-text query (all terms required)")] = "",
    category: Annotated[str | None, Query()] = None,
    subtype: Annotated[str | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
    kind: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> SearchResponse:
    """Run deterministic full-text search over the indexed records."""
    results = index.search(
        q, category=category, subtype=subtype, status=status, kind=kind, limit=limit
    )
    terms = [term for term in q.lower().split() if term]
    hits = [
        to_search_hit(record, score, make_snippet(record.content, terms))
        for score, record in results
    ]
    return SearchResponse(query=q, total=len(hits), hits=hits)


@api_router.get("/recent", tags=["brain"], response_model=RecentResponse)
def recent(
    index: IndexDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> RecentResponse:
    """Return the most recently modified records."""
    items = [to_summary(record) for record in index.recent(limit)]
    return RecentResponse(total=len(items), items=items)


@api_router.get("/overview", tags=["brain"], response_model=OverviewResponse)
def overview(index: IndexDep) -> OverviewResponse:
    """Return deterministic current totals for the Home overview."""
    return OverviewResponse(**index.overview())


@api_router.get("/changes", tags=["brain"], response_model=ChangesResponse)
def changes(
    index: IndexDep,
    since: Annotated[str | None, Query(description="ISO-8601 lower bound")] = None,
) -> ChangesResponse:
    """Return records modified in a time window with honest change labels."""
    known = set(ui_state.load().known)
    items = [
        ChangeItem(
            id=record.id,
            path=record.path,
            title=record.title,
            category=record.category,
            change_type="added" if record.id not in known else "modified",
            modified_at=record.modified_at,
        )
        for record in index.changes(since)
    ]
    return ChangesResponse(total=len(items), since=since, items=items)


@api_router.get("/graph", tags=["brain"], response_model=GraphResponse)
def graph(
    index: IndexDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    focus: Annotated[str | None, Query()] = None,
    depth: Annotated[int, Query(ge=1, le=3)] = 1,
    since: Annotated[str | None, Query()] = None,
) -> GraphResponse:
    """Project only explicit Brain relationships into a bounded graph."""
    if focus is not None and index.get(focus) is None:
        raise _record_not_found()
    return project_graph(index, limit=limit, focus=focus, depth=depth, since=since)


@api_router.get("/attention", tags=["brain"], response_model=AttentionResponse)
def attention(index: IndexDep, brain_path: BrainPathDep) -> AttentionResponse:
    """Project uncertainty already represented by Brain metadata and structure,
    plus notes due for review and notes that break the Brain's rules."""
    return compute_attention(index, brain=brain_path)


@api_router.get("/ui-state", tags=["system"], response_model=UiState)
def get_ui_state() -> UiState:
    """Read UI-only presentation state stored outside the Brain."""
    return ui_state.load()


@api_router.post("/ui-state", tags=["system"], response_model=UiState)
def post_ui_state(update: UiStateUpdate) -> UiState:
    """Persist UI-only presentation state outside the Brain."""
    if update.last_seen_at is not None and ui_state.parse_isodate(update.last_seen_at) is None:
        raise HTTPException(status_code=422, detail="last_seen_at must be an ISO-8601 timestamp")

    current = ui_state.load()
    merged = UiState(
        last_seen_at=(
            update.last_seen_at if update.last_seen_at is not None else current.last_seen_at
        ),
        known=current.known if update.known is None else list(dict.fromkeys(update.known)),
    )
    ui_state.save(merged)
    return merged


def _record_not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Record not found")


def _looks_invalid_id(record_id: str) -> bool:
    """Reject ids that cannot be valid catalog keys before lookup."""
    if not record_id or record_id != record_id.strip():
        return True
    if record_id.startswith("/") or "\\" in record_id or "\x00" in record_id:
        return True
    return any(segment in ("", ".", "..") for segment in record_id.split("/"))
