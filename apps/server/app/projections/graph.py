"""Relationship projection for the future 2D Brain Map (Phase 2).

Projects the Brain's **explicit** relationships into a small UI-oriented graph:
``{"nodes": [...], "edges": [...], "meta": {...}}``. Edges come only from
relationships already represented by the v1 index:

- resolved wikilinks  -> ``wikilink``
- resolved ``derived_from`` refs -> ``derived_from``

Nothing is invented: two notes are never connected because they "seem related",
no embeddings/LLM are used, and ``derived_from`` is *kept* as derivation
provenance — it is never relabeled ``evidence``/``supports``/``proves``.

The projection is deterministic and bounded. The UI must not render thousands of
nodes, so ``limit`` caps the returned node set; ``focus``+``depth`` return a
1/2-hop neighborhood of one record. Recent-change metadata reuses Phase 1's
time-window logic (see :meth:`BrainIndex.changes`) to mark nodes ``recent``.
Relationship *creation* times are not knowable from the index (it only records
per-file ``modified_at``), so edges carry no timestamp and that limitation is
exposed via ``meta.edge_creation_known == False`` rather than fabricated.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping

from brain_core.index import BrainIndex
from brain_core.records import Record

from ..api.models import GraphEdge, GraphMeta, GraphNode, GraphResponse

# Relationship types the graph will emit. `derived_from` is deliberately kept as
# derivation provenance (never relabeled to evidence/supports/proves).
TYPE_WIKILINK = "wikilink"
TYPE_DERIVED_FROM = "derived_from"


def _collect_edges(records: Mapping[str, Record]) -> list[tuple[str, str, str]]:
    """All explicit relationship edges, deduplicated and deterministically ordered.

    Edges are ``(source, target, type)`` where ``source`` is the record that
    declares the relationship and ``target`` is the resolved record. A wikilink
    and a ``derived_from`` between the same pair are distinct edges (different
    semantics). Self-relationships and unresolved references are skipped.
    """
    edges: set[tuple[str, str, str]] = set()
    for record in records.values():
        for link in record.links:
            if link.resolved_id and link.resolved_id != record.id:
                edges.add((record.id, link.resolved_id, TYPE_WIKILINK))
        for ref in record.derived_from_resolved:
            if ref.resolved_id and ref.resolved_id != record.id:
                edges.add((record.id, ref.resolved_id, TYPE_DERIVED_FROM))
    return sorted(edges, key=lambda e: (e[0], e[1], e[2]))


def _adjacency(edges: list[tuple[str, str, str]]) -> dict[str, set[str]]:
    """Undirected neighbor map over the collected edges (dedupes by target)."""
    adj: dict[str, set[str]] = defaultdict(set)
    for source, target, _ in edges:
        adj[source].add(target)
        adj[target].add(source)
    return adj


def _neighborhood(
    focus: str,
    edges: list[tuple[str, str, str]],
    adj: dict[str, set[str]],
    depth: int,
    limit: int,
) -> tuple[list[str], list[tuple[str, str, str]]]:
    """Deterministic BFS subgraph rooted at ``focus`` up to ``depth`` hops.

    Returns ``(nodes, edges)`` where nodes is an ordered, de-duplicated list
    rooted at ``focus`` (bounded to ``limit``) and edges only connect selected
    nodes. Iteration over neighbors is sorted so the result is stable/readable.
    """
    seen_list: list[str] = [focus]
    seen_set: set[str] = {focus}
    frontier: list[str] = [focus]
    for _ in range(depth):
        if len(seen_list) >= limit:
            break
        next_frontier: list[str] = []
        for node in frontier:
            for neighbor in sorted(adj.get(node, ())):
                if neighbor not in seen_set:
                    if len(seen_list) >= limit:
                        break
                    seen_set.add(neighbor)
                    seen_list.append(neighbor)
                    next_frontier.append(neighbor)
        frontier = next_frontier
        if not frontier:
            break

    selected = seen_list[:limit]
    selected_set = set(selected)
    kept = [e for e in edges if e[0] in selected_set and e[1] in selected_set]
    return selected, kept


def _overview(
    records: Mapping[str, Record],
    edges: list[tuple[str, str, str]],
    adj: dict[str, set[str]],
    limit: int,
) -> tuple[list[str], list[tuple[str, str, str]]]:
    """Compact overview: the most *connected* nodes (deterministic), then the
    edges between them.

    Node selection is purely a graph-layout heuristic (degree/connectivity so the
    future map stays readable) — it is *not* an epistemic importance ranking and
    implies nothing about knowledge quality. Sort is degree desc -> modified desc ->
    id asc (path tiebreak), mirroring the index's stable-sort conventions.
    """
    degree = {node: len(neighbors) for node, neighbors in adj.items()}
    ordered = list(adj.keys())
    # Stable sorts: id asc (final tiebreak), modified desc, then degree desc.
    ordered.sort(key=lambda n: n)
    ordered.sort(key=lambda n: records[n].modified_at or "", reverse=True)
    ordered.sort(key=lambda n: degree[n], reverse=True)

    selected = ordered[:limit]
    selected_set = set(selected)
    kept = [e for e in edges if e[0] in selected_set and e[1] in selected_set]
    return selected, kept


def _recent_ids(index: BrainIndex, since: str | None) -> set[str]:
    """Ids of records that changed within the ``since`` window, reusing Phase 1's
    time-window logic (:meth:`BrainIndex.changes`). Empty when no window given."""
    if since is None:
        return set()
    return {r.id for r in index.changes(since)}


def project_graph(
    index: BrainIndex,
    *,
    limit: int,
    focus: str | None = None,
    depth: int = 1,
    since: str | None = None,
) -> GraphResponse:
    """Build a bounded, read-only relationship projection of the Brain index."""
    # Hold one published mapping for the graph build. A concurrent watcher can
    # replace the catalog for the next request, but cannot mix snapshots inside
    # this projection.
    records = index.records
    edges = _collect_edges(records)
    adj = _adjacency(edges)
    recent_ids = _recent_ids(index, since)
    total_nodes = len(set().union(*(e[:2] for e in edges)) if edges else ())

    if focus is not None:
        selected, kept = _neighborhood(focus, edges, adj, depth, limit)
        mode = "focus"
    else:
        selected, kept = _overview(records, edges, adj, limit)
        mode = "overview"

    nodes: list[GraphNode] = []
    for node_id in selected:
        record = records[node_id]
        recent: bool | None = None if since is None else node_id in recent_ids
        nodes.append(
            GraphNode(
                id=record.id,
                title=record.title,
                category=record.category,
                subtype=record.subtype,
                status=record.status,
                modified_at=record.modified_at,
                recent=recent,
            )
        )

    graph_edges = [
        GraphEdge(source=source, target=target, type=etype) for source, target, etype in kept
    ]

    meta = GraphMeta(
        mode=mode,
        focus=focus,
        depth=depth if focus is not None else None,
        limit=limit,
        since=since,
        total_nodes=total_nodes,
        node_count=len(nodes),
        edge_count=len(graph_edges),
        edge_creation_known=False,  # honest: index has no per-edge timestamps
    )
    return GraphResponse(nodes=nodes, edges=graph_edges, meta=meta)
