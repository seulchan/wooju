"""Tests for Phase 1 overview / changes / ui-state endpoints."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.main import app

# Representative Brain with distinct categories and deterministic mtimes.
BRAIN_FILES = {
    "wiki/concepts/llm-agent-memory.md": (
        "---\ntitle: LLM Agent Memory\ntype: concept\n---\nNotes.\n"
    ),
    "wiki/insights/pattern.md": (
        "---\norigin: synthesis\nkind: pattern\nstatus: provisional\n"
        'derived_from: "wiki/concepts/llm-agent-memory"\n---\nPattern.\n'
    ),
    "wiki/insights/old.md": "---\norigin: synthesis\nstatus: established\n---\nOld insight.\n",
    "sources/paper.md": "---\ntitle: A Paper\n---\nSource.\n",
}
_BASE = 1_752_969_600  # 2026-08-08T00:00:00Z (approx epoch)
MTIMES = {
    "wiki/concepts/llm-agent-memory.md": _BASE - 15 * 86400,  # ~15 days ago
    "wiki/insights/pattern.md": _BASE - 2 * 86400,  # ~2 days ago
    "wiki/insights/old.md": _BASE - 90 * 86400,  # ~90 days ago
    "sources/paper.md": _BASE - 1 * 86400,  # ~1 day ago
}


def _client(monkeypatch, brain_path):
    monkeypatch.setenv("WOOJU_BRAIN_PATH", str(brain_path))
    return TestClient(app)


def _iso(epoch: int) -> str:
    return datetime.fromtimestamp(epoch, tz=UTC).isoformat()


# ---------------------------------------------------------------- overview


def test_overview_counts(make_brain, monkeypatch):
    brain = make_brain(BRAIN_FILES, mtimes=MTIMES)
    with _client(monkeypatch, brain) as client:
        data = client.get("/api/overview").json()
    assert data["knowledge"] == 1
    assert data["insight"] == 2
    assert data["source"] == 1
    assert data["provisional_insights"] == 1  # only status: provisional counts
    assert data["total"] == 4


def test_overview_empty_brain(make_brain, monkeypatch):
    brain = make_brain({})
    with _client(monkeypatch, brain) as client:
        data = client.get("/api/overview").json()
    assert data["knowledge"] == 0
    assert data["insight"] == 0
    assert data["source"] == 0
    assert data["provisional_insights"] == 0
    assert data["total"] == 0
    assert data["main_areas"] == []
    assert "indexed_at" in data


def test_overview_main_areas_grouped_by_wiki_subdir(make_brain, monkeypatch):
    """main_areas are deterministic knowledge groupings from the wiki subdirectory
    taxonomy, title-cased and ranked; surfaced only when ≥2 distinct areas."""
    files = {
        "wiki/concepts/a.md": "# A\n",
        "wiki/concepts/b.md": "# B\n",
        "wiki/overviews/o.md": "# O\n",
        "wiki/how-tos/h.md": "# H\n",
        # non-wiki knowledge-like paths and non-knowledge do not contribute.
        "sources/paper.md": "# Paper\n",
    }
    brain = make_brain(files)
    with _client(monkeypatch, brain) as client:
        data = client.get("/api/overview").json()
    areas = data["main_areas"]
    assert areas == [
        {"label": "Concepts", "count": 2},
        {"label": "How Tos", "count": 1},
        {"label": "Overviews", "count": 1},
    ]


def test_overview_main_areas_omitted_when_single_area(make_brain, monkeypatch):
    """A single knowledge area stays clean — no main_areas line."""
    brain = make_brain({"wiki/concepts/a.md": "# A\n", "wiki/concepts/b.md": "# B\n"})
    with _client(monkeypatch, brain) as client:
        data = client.get("/api/overview").json()
    assert data["main_areas"] == []


def test_other_classification_is_meta_content(make_brain, monkeypatch):
    """docs/, logs/, and root-level files are Brain system meta/documentation, not
    knowledge content — they have no place in the existing taxonomy and so classify
    as ``other``. They are never invented into a new category (no LLM, no fake
    taxonomy); Home instead keeps them out of prominence."""
    files = {
        "wiki/concepts/llm-agent-memory.md": "# LLM Agent Memory\n",
        "docs/KNOWLEDGE.md": "# Knowledge Layer\n",
        "logs/2026-08-08-ingest.md": "# 2026-08-08\n\n## ingest | things\n",
        "AGENTS.md": "# Agents\n",
        "README.md": "# wooju-brain\n",
        "index.md": "# Index\n",
    }
    brain = make_brain(files)
    with _client(monkeypatch, brain) as client:
        by_cat = client.get("/api/stats").json()["by_category"]
        items = client.get("/api/changes").json()["items"]
    assert by_cat.get("knowledge") == 1
    assert by_cat.get("other") == 5  # docs/, logs/, AGENTS, README, index
    # The other-categorized records are exactly the meta files.
    other_ids = {i["id"] for i in items if i["category"] == "other"}
    assert other_ids == {"docs/KNOWLEDGE", "logs/2026-08-08-ingest", "AGENTS", "README", "index"}
    # The log title is the entry H2, never the bare date.
    log_title = next(i["title"] for i in items if i["id"].startswith("logs/"))
    assert log_title == "ingest | things"


# ---------------------------------------------------------------- changes


def test_changes_all_time_defaults_to_added(make_brain, monkeypatch):
    brain = make_brain(BRAIN_FILES, mtimes=MTIMES)
    with _client(monkeypatch, brain) as client:
        data = client.get("/api/changes").json()
    assert data["total"] == 4
    assert data["since"] is None
    # First run: nothing is "known", so every record is honest "new to you".
    assert all(item["change_type"] == "added" for item in data["items"])
    # Newest first.
    assert data["items"][0]["id"] == "sources/paper"


def test_changes_since_window_filters_by_timestamp(make_brain, monkeypatch):
    brain = make_brain(BRAIN_FILES, mtimes=MTIMES)
    since = _iso(_BASE - 30 * 86400)  # last 30 days
    with _client(monkeypatch, brain) as client:
        data = client.get("/api/changes", params={"since": since}).json()
    ids = {item["id"] for item in data["items"]}
    assert ids == {
        "wiki/concepts/llm-agent-memory",  # 15d ago
        "wiki/insights/pattern",  # 2d ago
        "sources/paper",  # 1d ago
    }
    assert "wiki/insights/old" not in ids  # 90d ago excluded


def test_changes_seven_day_window(make_brain, monkeypatch):
    brain = make_brain(BRAIN_FILES, mtimes=MTIMES)
    since = _iso(_BASE - 7 * 86400)
    with _client(monkeypatch, brain) as client:
        data = client.get("/api/changes", params={"since": since}).json()
    ids = {item["id"] for item in data["items"]}
    assert ids == {"wiki/insights/pattern", "sources/paper"}  # 2d & 1d ago


def test_changes_known_records_marked_modified(make_brain, monkeypatch):
    """A record in the persisted `known` snapshot is 'modified', not 'added'."""
    brain = make_brain(BRAIN_FILES, mtimes=MTIMES)
    with _client(monkeypatch, brain) as client:
        client.post(
            "/api/ui-state",
            json={"known": ["sources/paper", "wiki/concepts/llm-agent-memory"]},
        )
        data = client.get("/api/changes").json()
    by_id = {item["id"]: item["change_type"] for item in data["items"]}
    assert by_id["sources/paper"] == "modified"
    assert by_id["wiki/concepts/llm-agent-memory"] == "modified"
    assert by_id["wiki/insights/pattern"] == "added"  # never seen before


# ---------------------------------------------------------------- ui-state


def test_ui_state_first_run_and_roundtrip(make_brain, monkeypatch):
    brain = make_brain(BRAIN_FILES, mtimes=MTIMES)
    with _client(monkeypatch, brain) as client:
        first = client.get("/api/ui-state").json()
        assert first == {"last_seen_at": None, "known": []}

        updated = client.post(
            "/api/ui-state",
            json={"last_seen_at": "2026-08-08T21:35:12+07:00", "known": ["a"]},
        ).json()
        assert updated["last_seen_at"] == "2026-08-08T21:35:12+07:00"
        assert updated["known"] == ["a"]

        # GET reflects persisted state (it lives outside the Brain).
        assert client.get("/api/ui-state").json() == updated


def test_ui_state_rejects_invalid_timestamp(make_brain, monkeypatch):
    brain = make_brain(BRAIN_FILES, mtimes=MTIMES)
    with _client(monkeypatch, brain) as client:
        resp = client.post("/api/ui-state", json={"last_seen_at": "yesterday"})
    assert resp.status_code == 422


def test_ui_state_partial_update_preserves_fields(make_brain, monkeypatch):
    brain = make_brain(BRAIN_FILES, mtimes=MTIMES)
    with _client(monkeypatch, brain) as client:
        client.post("/api/ui-state", json={"last_seen_at": "2026-08-08T00:00:00Z", "known": ["x"]})
        resp = client.post("/api/ui-state", json={"last_seen_at": "2026-08-09T00:00:00Z"}).json()
    assert resp["last_seen_at"] == "2026-08-09T00:00:00Z"
    assert resp["known"] == ["x"]  # omitted known preserved


# ---------------------------------------------------------------- invariants


def test_ui_state_written_outside_brain(make_brain, monkeypatch, tmp_path):
    """UI state persists to its own file, never into the Brain directory."""
    brain = make_brain(BRAIN_FILES, mtimes=MTIMES)
    state_path = tmp_path / "ui-state" / "state.json"
    monkeypatch.setenv("WOOJU_UI_STATE_PATH", str(state_path))
    with _client(monkeypatch, brain) as client:
        client.post("/api/ui-state", json={"last_seen_at": "2026-08-08T00:00:00Z"})
    assert state_path.exists()
    assert "last_seen_at" in state_path.read_text(encoding="utf-8")
    # No state file was created inside the Brain tree.
    assert not list(brain.rglob("*.json"))


def test_new_endpoints_never_mutate_brain(make_brain, monkeypatch, snapshot):
    brain = make_brain(BRAIN_FILES, mtimes=MTIMES)
    before = snapshot(brain)
    with _client(monkeypatch, brain) as client:
        client.get("/api/overview")
        client.get("/api/changes")
        client.get("/api/ui-state")
        client.post("/api/ui-state", json={"last_seen_at": "2026-08-08T00:00:00Z"})
        client.post("/api/ui-state", json={"known": ["wiki/insights/pattern"]})
    after = snapshot(brain)
    assert before == after


# ----------------------------------------------------------- last_seen_at lifecycle


def test_last_seen_at_two_session_sequence(make_brain, monkeypatch):
    """The full Since-last-visit lifecycle across two sessions.

    Session 1 (first run): no ``known`` snapshot, so every record is ``added``;
    Home then stamps ``last_seen_at`` and records the current id universe as
    ``known``. Session 2 (a new record exists since): only the genuinely new id
    is ``added``; everything previously seen is ``modified``. This proves the UI
    can tell new records from modified ones and that the comparison is anchored
    to the previous visit — never erased ahead of the current view.
    """
    brain = make_brain(BRAIN_FILES, mtimes=MTIMES)
    with _client(monkeypatch, brain) as client:
        # Session 1: first run — everything is new to you.
        first = client.get("/api/changes").json()
        assert {i["change_type"] for i in first["items"]} == {"added"}
        known_after_first = [i["id"] for i in first["items"]]
        client.post(
            "/api/ui-state",
            json={"last_seen_at": "2026-08-08T12:00:00Z", "known": known_after_first},
        )

        # Session 2: a brand-new note appears in the Brain since session 1.
        (brain / "wiki" / "concepts" / "brand-new.md").write_text("# Brand new\n", encoding="utf-8")
        # The watcher rescans in production; re-scan the app's in-memory index here.
        client.app.state.index.scan(brain)

        second = client.get("/api/changes").json()
        by_id = {i["id"]: i["change_type"] for i in second["items"]}
        assert by_id["wiki/concepts/brand-new"] == "added"  # genuinely new
        assert by_id["sources/paper"] == "modified"  # seen before
        assert by_id["wiki/insights/pattern"] == "modified"

        # The previous last_seen_at is still readable until the session finalizes
        # it — opening Home does not erase the prior comparison preemptively.
        assert client.get("/api/ui-state").json()["last_seen_at"] == "2026-08-08T12:00:00Z"
