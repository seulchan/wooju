"""Tests for Phase 4 "What needs attention?" (/api/attention and attention module).

The section must be deterministic and grounded only in semantics the Brain
already represents. These tests pin the epistemic discipline: provisional/
candidate lifecycle states surface, decided states (established/rejected/
superseded) do not, open questions are detected by the Brain's own location
convention, conflict is surfaced ONLY from an explicit ``epistemic.status:
contested`` (never inferred), and unresolved references exclude the Brain's own
``docs/`` meta-documentation. No confidence/quality scoring is invented.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

# A Brain exercising every attention category plus the must-NOT-surface cases.
#
#   wiki/insights/prov.md    origin: synthesis, status: provisional  -> provisional
#   wiki/insights/cand.md    origin: synthesis, status: candidate    -> candidate
#   wiki/insights/est.md     origin: synthesis, status: established  -> (NOT surfaced)
#   wiki/insights/rej.md     origin: synthesis, status: rejected     -> (NOT surfaced)
#   wiki/insights/sup.md     origin: synthesis, status: superseded   -> (NOT surfaced)
#   wiki/insights/cont.md    origin: synthesis, status: provisional,
#                            epistemic.status: contested             -> contested (+ provisional)
#   wiki/questions/q.md      open question by location               -> open_questions
#   wiki/notes/typed-q.md    type: question                          -> open_questions
#   wiki/notes/real.md       body wikilink to a missing note         -> unresolved_links
#   wiki/insights/baddf.md   derived_from to a missing note          -> unresolved_derived_from
#   docs/guide.md            illustrative wikilink to a missing note -> (NOT surfaced; docs/)
BRAIN_FILES = {
    "wiki/insights/prov.md": (
        "---\norigin: synthesis\nstatus: provisional\ninsight_kind: pattern\n---\nA.\n"
    ),
    "wiki/insights/cand.md": (
        "---\norigin: synthesis\nstatus: candidate\ninsight_kind: connection\n---\nB.\n"
    ),
    "wiki/insights/est.md": (
        "---\norigin: synthesis\nstatus: established\ninsight_kind: pattern\n---\nC.\n"
    ),
    "wiki/insights/rej.md": "---\norigin: synthesis\nstatus: rejected\n---\nD.\n",
    "wiki/insights/sup.md": "---\norigin: synthesis\nstatus: superseded\n---\nE.\n",
    "wiki/insights/cont.md": (
        "---\n"
        "origin: synthesis\n"
        "status: provisional\n"
        "insight_kind: tension\n"
        "epistemic:\n"
        "  mode: rigorous\n"
        "  status: contested\n"
        "  evidence_strength: low\n"
        "---\nF.\n"
    ),
    "wiki/questions/q.md": "---\ntitle: Open Q\ntype: concept\n---\n## Question\nWhy?\n",
    "wiki/notes/typed-q.md": "---\ntype: question\n---\nAnother open question.\n",
    "wiki/notes/real.md": "---\ntype: concept\n---\nSee [[notes/missing]].\n",
    "wiki/insights/baddf.md": (
        "---\norigin: synthesis\nstatus: candidate\n"
        'derived_from: ["[[concepts/ghost]]"]\n---\nDerived from a ghost.\n'
    ),
    "docs/guide.md": "# Guide\nExample link [[concepts/illustrative]].\n",
}


def _client(monkeypatch, brain_path):
    monkeypatch.setenv("WOOJU_BRAIN_PATH", str(brain_path))
    return TestClient(app)


def _by_key(data):
    return {g["key"]: g for g in data["groups"]}


# ----------------------------------------------------------------- categories


def test_provisional_and_candidate_surface(make_brain, monkeypatch):
    brain = make_brain(BRAIN_FILES)
    with _client(monkeypatch, brain) as client:
        data = client.get("/api/attention").json()
    groups = _by_key(data)
    prov_ids = {i["id"] for i in groups["provisional"]["items"]}
    cand_ids = {i["id"] for i in groups["candidate"]["items"]}
    assert "wiki/insights/prov" in prov_ids
    # The contested insight is also lifecycle-provisional -> it belongs here too.
    assert "wiki/insights/cont" in prov_ids
    assert groups["provisional"]["count"] == 2
    assert "wiki/insights/cand" in cand_ids
    assert groups["candidate"]["count"] == 2  # cand + baddf (both candidate)


def test_decided_lifecycle_states_are_not_surfaced(make_brain, monkeypatch):
    """established/rejected/superseded are decided outcomes, not open uncertainty."""
    brain = make_brain(BRAIN_FILES)
    with _client(monkeypatch, brain) as client:
        data = client.get("/api/attention").json()
    decided = {"wiki/insights/est", "wiki/insights/rej", "wiki/insights/sup"}
    lifecycle = {
        i["id"]
        for g in data["groups"]
        for i in g["items"]
        if g["key"] in ("provisional", "candidate")
    }
    assert not (decided & lifecycle)


def test_open_questions_by_location_and_by_subtype(make_brain, monkeypatch):
    brain = make_brain(BRAIN_FILES)
    with _client(monkeypatch, brain) as client:
        data = client.get("/api/attention").json()
    groups = _by_key(data)
    q_ids = {i["id"] for i in groups["open_questions"]["items"]}
    assert "wiki/questions/q" in q_ids  # questions/ directory convention
    assert "wiki/notes/typed-q" in q_ids  # subtype/type: question
    assert groups["open_questions"]["count"] == 2


def test_contested_only_from_explicit_epistemic_status(make_brain, monkeypatch):
    """Conflict must come from explicit epistemic.status: contested, never inferred."""
    brain = make_brain(BRAIN_FILES)
    with _client(monkeypatch, brain) as client:
        data = client.get("/api/attention").json()
    groups = _by_key(data)
    contested_ids = {i["id"] for i in groups["contested"]["items"]}
    assert contested_ids == {"wiki/insights/cont"}
    # A provisional lifecycle (cont record) must NOT be misread as contested by
    # itself; only the nested epistemic.status does. No other record is contested.
    assert groups["contested"]["count"] == 1


def test_unresolved_derived_from(make_brain, monkeypatch):
    brain = make_brain(BRAIN_FILES)
    with _client(monkeypatch, brain) as client:
        data = client.get("/api/attention").json()
    groups = _by_key(data)
    items = groups["unresolved_derived_from"]["items"]
    assert any(
        i["id"] == "wiki/insights/baddf" and i["detail"] == "[[concepts/ghost]]" for i in items
    )
    assert groups["unresolved_derived_from"]["count"] == 1


def test_unresolved_links_exclude_docs_meta_documentation(make_brain, monkeypatch):
    """docs/ illustrative wikilinks are not broken knowledge -> not surfaced."""
    brain = make_brain(BRAIN_FILES)
    with _client(monkeypatch, brain) as client:
        data = client.get("/api/attention").json()
    groups = _by_key(data)
    link_items = groups["unresolved_links"]["items"]
    surfaced_ids = {i["id"] for i in link_items}
    # The real knowledge note with a broken wikilink IS surfaced ...
    assert "wiki/notes/real" in surfaced_ids
    assert any(i["id"] == "wiki/notes/real" and i["detail"] == "notes/missing" for i in link_items)
    # ... but the docs/ guide example is NOT.
    assert "docs/guide" not in surfaced_ids
    assert all(i["category"] != "other" for i in link_items)


def test_unresolved_links_dedupe_same_target_within_record(make_brain, monkeypatch):
    files = {
        "wiki/notes/dup.md": "---\ntype: concept\n---\n[[missing]] and again [[missing]].\n",
    }
    brain = make_brain(files)
    with _client(monkeypatch, brain) as client:
        data = client.get("/api/attention").json()
    groups = _by_key(data)
    dup_items = [i for i in groups["unresolved_links"]["items"] if i["id"] == "wiki/notes/dup"]
    assert len(dup_items) == 1


# ----------------------------------------------------------------- discipline


def test_no_confidence_or_score_fields(make_brain, monkeypatch):
    """The response carries no invented confidence/health/quality scoring."""
    brain = make_brain(BRAIN_FILES)
    with _client(monkeypatch, brain) as client:
        data = client.get("/api/attention").json()

    forbidden = {"score", "confidence", "health", "quality", "severity", "priority"}

    def _check(obj, path):
        if isinstance(obj, dict):
            assert not (set(obj.keys()) & forbidden), f"forbidden field at {path}"
            for k, v in obj.items():
                _check(v, f"{path}.{k}")
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                _check(v, f"{path}[{i}]")

    _check(data, "root")


def test_group_order_is_canonical(make_brain, monkeypatch):
    brain = make_brain(BRAIN_FILES)
    with _client(monkeypatch, brain) as client:
        data = client.get("/api/attention").json()
    keys = [g["key"] for g in data["groups"]]
    # Returned groups are a subsequence of the canonical order.
    canonical = [
        "review_due",
        "rule_errors",
        "provisional",
        "candidate",
        "open_questions",
        "contested",
        "unresolved_derived_from",
        "unresolved_links",
    ]
    assert keys == [k for k in canonical if k in set(keys)]


def test_total_is_sum_of_group_counts(make_brain, monkeypatch):
    brain = make_brain(BRAIN_FILES)
    with _client(monkeypatch, brain) as client:
        data = client.get("/api/attention").json()
    assert data["total"] == sum(g["count"] for g in data["groups"])


# ----------------------------------------------------------------- robustness


def test_empty_brain_returns_no_groups(make_brain, monkeypatch):
    brain = make_brain({})
    with _client(monkeypatch, brain) as client:
        data = client.get("/api/attention").json()
    assert data == {"groups": [], "total": 0}


def test_attention_is_deterministic(make_brain, monkeypatch):
    brain = make_brain(BRAIN_FILES)
    with _client(monkeypatch, brain) as client:
        first = client.get("/api/attention").json()
        second = client.get("/api/attention").json()
    assert first == second


def test_unresolved_group_items_trimmed_but_count_true(make_brain, monkeypatch):
    """Many unresolved links: count reports the true total, items are trimmed."""
    files = {f"wiki/notes/n{i}.md": f"---\ntype: concept\n---\n[[ghost-{i}]].\n" for i in range(30)}
    brain = make_brain(files)
    with _client(monkeypatch, brain) as client:
        data = client.get("/api/attention").json()
    groups = _by_key(data)
    links = groups["unresolved_links"]
    assert links["count"] == 30
    assert len(links["items"]) <= 12  # trimmed to keep the section actionable
    assert len(links["items"]) < links["count"]


def test_attention_api_never_mutates_brain(make_brain, monkeypatch, snapshot):
    brain = make_brain(BRAIN_FILES)
    before = snapshot(brain)
    with _client(monkeypatch, brain) as client:
        client.get("/api/attention")
        client.get("/api/attention")  # idempotent reads
    after = snapshot(brain)
    assert before == after
