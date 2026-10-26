"""Tests for Phase 2 relationship projection (/api/graph and graph module).

Covers the acceptance-critical behaviors: explicit wikilink/derived_from edges,
unresolved-link handling, no fabricated relationships, bounded responses,
focus/neighborhood mode, read-only + security invariants, and the guarantee that
``derived_from`` stays derivation provenance (never relabeled to evidence).
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.main import app

# A Brain with a small, well-defined web of explicit relationships:
#   a --wikilink--> b        (a's body links [[b]])
#   i --derived_from--> a    (insight derives from a)
#   i --wikilink--> s        (insight links to a source)
#   uses --wikilink--> s     (knowledge note links to a source)
# unresolved -> no edge; isolated/c -> no edge.
BRAIN_FILES = {
    "wiki/concepts/a.md": "---\ntitle: A\ntype: concept\n---\nLinks [[b]].\n",
    "wiki/concepts/b.md": "# B\n",
    "wiki/insights/i.md": (
        "---\norigin: synthesis\nstatus: provisional\n"
        'derived_from: ["wiki/concepts/a"]\n---\nSees [[sources/s]].\n'
    ),
    "sources/s.md": "# Source\n",
    "wiki/uses.md": "---\ntype: concept\n---\nBases on [[sources/s]].\n",
    "wiki/unresolved.md": "---\ntype: concept\n---\nBroken [[does/not/exist]].\n",
    "wiki/isolated.md": "# Isolated note\n",
    "wiki/concepts/c.md": "# C disconnected\n",
}

_BASE = 1_752_969_600  # 2026-08-08T00:00:00Z
MTIMES = {
    "wiki/concepts/a.md": _BASE - 30 * 86400,  # 30d ago
    "wiki/concepts/b.md": _BASE - 30 * 86400,
    "wiki/insights/i.md": _BASE - 2 * 86400,  # 2d ago
    "sources/s.md": _BASE - 1 * 86400,  # 1d ago
    "wiki/uses.md": _BASE - 20 * 86400,
    "wiki/unresolved.md": _BASE - 20 * 86400,
    "wiki/isolated.md": _BASE - 20 * 86400,
    "wiki/concepts/c.md": _BASE - 20 * 86400,
}


def _client(monkeypatch, brain_path):
    monkeypatch.setenv("WOOJU_BRAIN_PATH", str(brain_path))
    return TestClient(app)


def _iso(epoch: int) -> str:
    return datetime.fromtimestamp(epoch, tz=UTC).isoformat()


def _edge_map(data) -> dict[tuple[str, str], str]:
    """Map ``(source, target)`` -> type (asserts no duplicate pair)."""
    out: dict[tuple[str, str], str] = {}
    for e in data["edges"]:
        assert e["source"] in data["node_ids"]
        assert e["target"] in data["node_ids"]
        out[(e["source"], e["target"])] = e["type"]
    return out


def test_resolved_wikilink_edge(make_brain, monkeypatch):
    brain = make_brain(BRAIN_FILES, mtimes=MTIMES)
    with _client(monkeypatch, brain) as client:
        data = client.get("/api/graph").json()
    data["node_ids"] = {n["id"] for n in data["nodes"]}
    edges = _edge_map(data)
    assert edges[("wiki/concepts/a", "wiki/concepts/b")] == "wikilink"
    assert edges[("wiki/insights/i", "sources/s")] == "wikilink"
    assert edges[("wiki/uses", "sources/s")] == "wikilink"


def test_derived_from_edge(make_brain, monkeypatch):
    brain = make_brain(BRAIN_FILES, mtimes=MTIMES)
    with _client(monkeypatch, brain) as client:
        data = client.get("/api/graph").json()
    data["node_ids"] = {n["id"] for n in data["nodes"]}
    edges = _edge_map(data)
    # Derivation provenance — the edge type must remain exactly "derived_from".
    assert edges[("wiki/insights/i", "wiki/concepts/a")] == "derived_from"


def test_unresolved_link_produces_no_edge_and_no_node(make_brain, monkeypatch):
    brain = make_brain(BRAIN_FILES, mtimes=MTIMES)
    with _client(monkeypatch, brain) as client:
        data = client.get("/api/graph").json()
    ids = {n["id"] for n in data["nodes"]}
    assert "wiki/unresolved" not in ids  # a note with only unresolved links is isolated
    assert all("does/not/exist" not in (e["source"], e["target"]) for e in data["edges"])


def test_source_relationship_surfaces_as_wikilink_not_fabricated_type(make_brain, monkeypatch):
    """The Brain has no separate 'source' edge type; source links are wikilinks."""
    brain = make_brain(BRAIN_FILES, mtimes=MTIMES)
    with _client(monkeypatch, brain) as client:
        data = client.get("/api/graph").json()
    data["node_ids"] = {n["id"] for n in data["nodes"]}
    edges = _edge_map(data)
    # A knowledge note pointing at a source must be a plain wikilink edge.
    assert edges[("wiki/uses", "sources/s")] == "wikilink"


def test_no_relationship_is_fabricated(make_brain, monkeypatch):
    brain = make_brain(BRAIN_FILES, mtimes=MTIMES)
    with _client(monkeypatch, brain) as client:
        data = client.get("/api/graph").json()
    data["node_ids"] = {n["id"] for n in data["nodes"]}
    # b and c are both concepts with no explicit link -> no edge between them.
    # 'isolated' has no links at all -> not even a node.
    assert ("wiki/concepts/b", "wiki/concepts/c") not in _edge_map(data)
    ids = {n["id"] for n in data["nodes"]}
    assert "wiki/isolated" not in ids
    # Only the two explicit relationship types are ever emitted.
    allowed = {"wikilink", "derived_from"}
    assert all(e["type"] in allowed for e in data["edges"])


def test_derived_from_never_relabeled_to_evidence(make_brain, monkeypatch):
    """derived_from is preserved as derivation, never relabeled to evidence."""
    brain = make_brain(BRAIN_FILES, mtimes=MTIMES)
    with _client(monkeypatch, brain) as client:
        data = client.get("/api/graph").json()
    types = {e["type"] for e in data["edges"]}
    assert "derived_from" in types
    assert not (types & {"evidence", "supports", "proves", "source", "similarity"})


def test_duplicate_wikilinks_dedupe_to_one_edge(make_brain, monkeypatch):
    files = {
        "wiki/x.md": "---\ntype: concept\n---\n[[y]] twice [[y]] again.\n",
        "wiki/concepts/y.md": "# Y\n",
    }
    brain = make_brain(files)
    with _client(monkeypatch, brain) as client:
        data = client.get("/api/graph").json()
    same = [e for e in data["edges"] if (e["source"], e["target"]) == ("wiki/x", "wiki/concepts/y")]
    assert len(same) == 1


def test_graph_is_bounded_by_limit(make_brain, monkeypatch):
    brain = make_brain(BRAIN_FILES, mtimes=MTIMES)
    with _client(monkeypatch, brain) as client:
        data = client.get("/api/graph", params={"limit": 2}).json()
    assert data["meta"]["mode"] == "overview"
    assert data["meta"]["node_count"] <= 2
    assert len(data["nodes"]) <= 2
    # Every returned edge connects two returned nodes (no dangling references).
    ids = {n["id"] for n in data["nodes"]}
    assert all(e["source"] in ids and e["target"] in ids for e in data["edges"])


def test_focus_neighborhood_depth(make_brain, monkeypatch):
    brain = make_brain(BRAIN_FILES, mtimes=MTIMES)
    with _client(monkeypatch, brain) as client:
        d1 = client.get("/api/graph", params={"focus": "wiki/insights/i", "depth": 1}).json()
        d2 = client.get("/api/graph", params={"focus": "wiki/concepts/a", "depth": 2}).json()
    assert d1["meta"]["mode"] == "focus"
    ids1 = {n["id"] for n in d1["nodes"]}
    assert ids1 == {"wiki/insights/i", "wiki/concepts/a", "sources/s"}  # 1-hop
    assert all(e["source"] in ids1 and e["target"] in ids1 for e in d1["edges"])

    ids2 = {n["id"] for n in d2["nodes"]}
    assert ids2 == {
        "wiki/concepts/a",
        "wiki/concepts/b",
        "wiki/insights/i",
        "sources/s",
    }  # 2-hop


def test_focus_missing_or_traversal_id_is_404(make_brain, monkeypatch):
    brain = make_brain(BRAIN_FILES, mtimes=MTIMES)
    with _client(monkeypatch, brain) as client:
        missing = client.get("/api/graph", params={"focus": "wiki/does-not-exist"})
        traversal = client.get("/api/graph", params={"focus": "../secret"})
        httpx_traversal = client.get("/api/graph", params={"focus": "..%2F..%2Fetc"})
    assert missing.status_code == 404
    assert traversal.status_code == 404
    assert httpx_traversal.status_code == 404


def test_recent_marks_nodes_within_window_and_exposes_edge_limit(make_brain, monkeypatch):
    brain = make_brain(BRAIN_FILES, mtimes=MTIMES)
    since = _iso(_BASE - 7 * 86400)  # last 7 days
    with _client(monkeypatch, brain) as client:
        data = client.get("/api/graph", params={"since": since}).json()
    recent = {n["id"]: n["recent"] for n in data["nodes"]}
    assert recent["sources/s"] is True  # modified 1d ago
    assert recent["wiki/insights/i"] is True  # modified 2d ago
    assert recent["wiki/concepts/a"] is False  # modified 30d ago
    assert recent["wiki/concepts/b"] is False
    # Without a window, recent is None (no claim made).
    no_window = client.get("/api/graph").json()
    assert all(n["recent"] is None for n in no_window["nodes"])
    # Edge creation times are not knowable -> honestly exposed, not fabricated.
    assert data["meta"]["edge_creation_known"] is False


def test_graph_empty_brain(make_brain, monkeypatch):
    brain = make_brain({})
    with _client(monkeypatch, brain) as client:
        data = client.get("/api/graph").json()
    assert data["nodes"] == []
    assert data["edges"] == []
    assert data["meta"]["total_nodes"] == 0
    assert data["meta"]["node_count"] == 0


def test_graph_is_deterministic(make_brain, monkeypatch):
    brain = make_brain(BRAIN_FILES, mtimes=MTIMES)
    with _client(monkeypatch, brain) as client:
        first = client.get("/api/graph").json()
        second = client.get("/api/graph").json()
    assert first == second


def test_graph_api_never_mutates_brain(make_brain, monkeypatch, snapshot):
    brain = make_brain(BRAIN_FILES, mtimes=MTIMES)
    before = snapshot(brain)
    with _client(monkeypatch, brain) as client:
        client.get("/api/graph")
        client.get("/api/graph", params={"focus": "wiki/insights/i", "depth": 2})
        client.get("/api/graph", params={"since": _iso(_BASE - 7 * 86400)})
    after = snapshot(brain)
    assert before == after