"""Integration tests for the Phase 2 read endpoints via TestClient."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

# A representative Brain exercising most categories/fields.
BRAIN_FILES = {
    "wiki/concepts/llm-agent-memory.md": (
        "---\ntitle: LLM Agent Memory\ntype: concept\naliases: [Agent Memory]\n---\n"
        "Notes on agent memory systems.\n"
    ),
    "wiki/insights/pattern.md": (
        "---\norigin: synthesis\nkind: pattern\nstatus: provisional\n"
        'derived_from: "wiki/concepts/llm-agent-memory"\n---\n'
        "A derived pattern about memory.\n"
    ),
    "sources/paper.md": "---\ntitle: A Paper\n---\nSource note text.\n",
    "memory/note.md": "# A Memory",
}


def _client(monkeypatch, brain_path):
    monkeypatch.setenv("WOOJU_BRAIN_PATH", str(brain_path))
    return TestClient(app)


# --------------------------------------------------------------- stats


def test_stats(make_brain, monkeypatch):
    brain = make_brain(BRAIN_FILES)
    with _client(monkeypatch, brain) as client:
        data = client.get("/api/stats").json()
    assert data["total"] == 4
    assert data["by_category"]["knowledge"] == 1
    assert data["by_category"]["insight"] == 1
    assert data["by_category"]["source"] == 1
    assert data["by_category"]["memory"] == 1
    assert data["by_status"]["provisional"] == 1
    assert "earliest" in data["modified_range"]


# --------------------------------------------------------------- lists + filters


def test_knowledge_and_subtype_filter(make_brain, monkeypatch):
    brain = make_brain(BRAIN_FILES)
    with _client(monkeypatch, brain) as client:
        all_knowledge = client.get("/api/knowledge").json()
        concepts = client.get("/api/knowledge", params={"subtype": "concept"}).json()
    assert all_knowledge["total"] == 1
    assert all_knowledge["items"][0]["id"] == "wiki/concepts/llm-agent-memory"
    assert concepts["total"] == 1
    assert concepts["items"][0]["subtype"] == "concept"


def test_insights_and_status_filter(make_brain, monkeypatch):
    brain = make_brain(BRAIN_FILES)
    with _client(monkeypatch, brain) as client:
        insights = client.get("/api/insights").json()
        provisional = client.get("/api/insights", params={"status": "provisional"}).json()
        established = client.get("/api/insights", params={"status": "established"}).json()
    assert insights["total"] == 1
    assert insights["items"][0]["kind"] == "pattern"
    assert provisional["total"] == 1
    assert established["total"] == 0  # established is never inferred


def test_sources(make_brain, monkeypatch):
    brain = make_brain(BRAIN_FILES)
    with _client(monkeypatch, brain) as client:
        data = client.get("/api/sources").json()
    assert data["total"] == 1
    assert data["items"][0]["id"] == "sources/paper"


# --------------------------------------------------------------- record by id


def test_get_record_nested_and_404(make_brain, monkeypatch):
    brain = make_brain(BRAIN_FILES)
    with _client(monkeypatch, brain) as client:
        rec = client.get("/api/records/wiki/concepts/llm-agent-memory").json()
        missing = client.get("/api/records/wiki/does-not-exist")
    assert rec["id"] == "wiki/concepts/llm-agent-memory"
    assert rec["title"] == "LLM Agent Memory"
    assert rec["category"] == "knowledge"
    assert rec["aliases"] == ["Agent Memory"]
    assert rec["links"] == []  # this note has no wikilinks
    assert missing.status_code == 404


def test_record_exposes_derived_from_and_links(make_brain, monkeypatch):
    brain = make_brain(BRAIN_FILES)
    with _client(monkeypatch, brain) as client:
        insight = client.get("/api/records/wiki/insights/pattern").json()
    assert insight["derived_from"] == ["wiki/concepts/llm-agent-memory"]
    resolved = insight["derived_from_resolved"]
    assert resolved[0]["ref"] == "wiki/concepts/llm-agent-memory"
    assert resolved[0]["resolved_id"] == "wiki/concepts/llm-agent-memory"


def test_summary_exposes_excerpt_and_derived_from_count(make_brain, monkeypatch):
    """List summaries carry a body excerpt and derivation count (Phase 3 cards)."""
    brain = make_brain(BRAIN_FILES)
    with _client(monkeypatch, brain) as client:
        knowledge = client.get("/api/knowledge").json()
        insights = client.get("/api/insights").json()
    k = knowledge["items"][0]
    assert k["excerpt"] == "Notes on agent memory systems."
    assert k["derived_from_count"] == 0

    ins = insights["items"][0]
    assert ins["derived_from_count"] == 1  # the pattern derives from one record
    assert isinstance(ins["excerpt"], str) and ins["excerpt"]


# --------------------------------------------------------------- path traversal


def test_path_traversal_rejected(make_brain, monkeypatch):
    brain = make_brain(BRAIN_FILES)
    attacks = [
        "/api/records/..%2F..%2Fetc%2Fpasswd",
        "/api/records/%2e%2e/%2e%2e/etc/passwd",
        "/api/records/%2Fetc%2Fpasswd",
        "/api/records/x%00y",
        "/api/records/",
        "/api/records/../../etc/passwd",
    ]
    with _client(monkeypatch, brain) as client:
        for url in attacks:
            resp = client.get(url)
            assert resp.status_code == 404, f"{url} returned {resp.status_code}"
            assert b"passwd" not in resp.content


# --------------------------------------------------------------- search


def test_search_hit_miss_and_blank(make_brain, monkeypatch):
    brain = make_brain(BRAIN_FILES)
    with _client(monkeypatch, brain) as client:
        hit = client.get("/api/search", params={"q": "agent memory"}).json()
        alias_hit = client.get("/api/search", params={"q": "Agent Memory"}).json()
        miss = client.get("/api/search", params={"q": "zzznope"}).json()
        blank = client.get("/api/search", params={"q": ""}).json()
    assert hit["total"] >= 1
    assert any(h["id"] == "wiki/concepts/llm-agent-memory" for h in hit["hits"])
    assert alias_hit["total"] >= 1  # alias match
    assert miss["total"] == 0
    assert blank["total"] == 0


def test_search_preserves_insight_status(make_brain, monkeypatch):
    """Search hits carry the insight lifecycle status (not surfaced for others)."""
    brain = make_brain(BRAIN_FILES)
    with _client(monkeypatch, brain) as client:
        data = client.get("/api/search", params={"q": "pattern"}).json()
    insight_hit = next(h for h in data["hits"] if h["id"] == "wiki/insights/pattern")
    assert insight_hit["status"] == "provisional"
    assert insight_hit["kind"] == "pattern"
    # A knowledge hit has no epistemic status.
    knowledge_hit = next(
        (h for h in data["hits"] if h["id"] == "wiki/concepts/llm-agent-memory"), None
    )
    if knowledge_hit:
        assert knowledge_hit["status"] is None


def test_health_and_stats_expose_indexed_at(make_brain, monkeypatch):
    brain = make_brain(BRAIN_FILES)
    with _client(monkeypatch, brain) as client:
        health = client.get("/api/health").json()
        stats = client.get("/api/stats").json()
    assert health["brain_valid"] is True
    assert isinstance(health["indexed_at"], str) and health["indexed_at"]
    assert stats["indexed_at"] == health["indexed_at"]


def test_recent(make_brain, monkeypatch):
    brain = make_brain(
        BRAIN_FILES,
        mtimes={
            "wiki/concepts/llm-agent-memory.md": 1_000_000,
            "wiki/insights/pattern.md": 1_500_000,
            "memory/note.md": 2_000_000,
            "sources/paper.md": 3_000_000,
        },
    )
    with _client(monkeypatch, brain) as client:
        data = client.get("/api/recent", params={"limit": 2}).json()
    assert data["total"] == 2
    assert data["items"][0]["id"] == "sources/paper"  # newest mtime first
    assert data["items"][1]["id"] == "memory/note"


# --------------------------------------------------------------- graceful degradation


def test_empty_brain_returns_empty_results(make_brain, monkeypatch):
    brain = make_brain({})
    with _client(monkeypatch, brain) as client:
        for url in ["/api/stats", "/api/knowledge", "/api/insights", "/api/sources", "/api/recent"]:
            resp = client.get(url)
            assert resp.status_code == 200, url
            assert resp.json()["total"] == 0, url
        assert client.get("/api/search", params={"q": "x"}).json()["total"] == 0


def test_misconfigured_brain_returns_empty_results(monkeypatch):
    monkeypatch.delenv("WOOJU_BRAIN_PATH", raising=False)
    with TestClient(app) as client:
        for url in ["/api/stats", "/api/knowledge", "/api/insights", "/api/sources"]:
            resp = client.get(url)
            assert resp.status_code == 200, url
            assert resp.json()["total"] == 0, url
        assert client.get("/api/records/anything").status_code == 404


# --------------------------------------------------------------- no mutation


def test_api_never_mutates_brain(make_brain, monkeypatch, snapshot):
    brain = make_brain(BRAIN_FILES)
    before = snapshot(brain)
    with _client(monkeypatch, brain) as client:
        client.get("/api/stats")
        client.get("/api/knowledge")
        client.get("/api/insights")
        client.get("/api/sources")
        client.get("/api/recent")
        client.get("/api/search", params={"q": "memory"})
        client.get("/api/records/wiki/concepts/llm-agent-memory")
    after = snapshot(brain)
    assert before == after
