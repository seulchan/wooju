"""The review gate is measured: every decision on a proposal is logged."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app import approvals
from app.main import app
from brain_core.changes import FileChange, Proposal


def proposal(agent: str = "ingest", via: str | None = None) -> Proposal:
    return Proposal(
        agent=agent,
        title="t",
        changes=[FileChange(op="write", path="wiki/concepts/x.md", content="x")],
        via=via,  # type: ignore[arg-type]
    )


def test_every_proposal_knows_how_it_arrived():
    assert proposal("you").via == "you"
    assert proposal("claude").via == "claude"
    assert proposal("ingest").via == "app"
    assert proposal("ingest", "telegram").via == "telegram"
    assert proposal("topics").via == "wooju"


def test_summary_counts_decisions_and_flags_a_rubber_stamp():
    for _ in range(19):
        approvals.record(proposal(via="telegram"), "approved")
    approvals.record(proposal("topics"), "rejected", batch=True)
    s = approvals.summary()
    assert s["total"] == 20 and s["approved"] == 19 and s["rejected"] == 1 and s["batch"] == 1
    assert s["approved_rate"] == 0.95 and s["rubber_stamp"] is True
    assert s["external"]["total"] == 19  # telegram is outside material; topics is not


def test_too_few_decisions_are_not_judged_and_old_ones_drop_out():
    for _ in range(5):
        approvals.record(proposal(), "approved")
    assert approvals.summary()["rubber_stamp"] is False
    later = datetime.now(UTC) + timedelta(days=31)
    assert approvals.summary(now=later)["total"] == 0


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.delenv("WOOJU_BRAIN_PATH", raising=False)
    with TestClient(app) as c:
        assert c.post("/api/setup/brain", json={"path": str(tmp_path / "B")}).status_code == 200
        yield c


def test_approving_editing_and_rejecting_are_logged(client):
    store = client.app.state.engine.store
    note = "---\ntitle: X\n---\n# X\n\n## What it is\n\nA thing.\n"
    a = store.save(
        Proposal(
            agent="claude",
            title="a",
            approval="batch",
            changes=[FileChange(op="write", path="wiki/concepts/a.md", content=note)],
        )
    )
    b = store.save(
        Proposal(
            agent="claude",
            title="b",
            approval="batch",
            changes=[FileChange(op="write", path="wiki/concepts/b.md", content=note)],
        )
    )
    assert client.post(f"/api/proposals/{a.id}/edit", json={"body": "Better."}).status_code == 200
    assert client.post(f"/api/proposals/{a.id}/approve").json()["status"] == "applied"
    assert client.post(f"/api/proposals/{b.id}/reject").json()["status"] == "rejected"
    s = client.get("/api/approvals").json()
    assert (s["edited"], s["rejected"], s["approved"]) == (1, 1, 0)
    assert s["external"]["total"] == 2  # Claude's writes are outside material


def test_a_pending_change_to_an_existing_note_shows_its_diff(client, tmp_path):
    brain = tmp_path / "B"
    (brain / "wiki/concepts").mkdir(parents=True, exist_ok=True)
    old = "---\ntitle: X\n---\n# X\n\n## What it is\n\nA thing.\n"
    (brain / "wiki/concepts/x.md").write_text(old, encoding="utf-8")
    client.app.state.engine.store.save(
        Proposal(
            agent="claude",
            title="x",
            approval="batch",
            changes=[
                FileChange(
                    op="write",
                    path="wiki/concepts/x.md",
                    content=old.replace("A thing.", "Two things."),
                ),
                FileChange(op="write", path="wiki/concepts/new.md", content=old),
            ],
        )
    )
    [card] = client.get("/api/proposals?status=pending").json()["items"]
    edit, new = card["changes"]
    assert {"kind": "remove", "text": "A thing."} in edit["diff"]
    assert {"kind": "add", "text": "Two things."} in edit["diff"]
    assert new["diff"] is None  # a new note has nothing to compare with
    assert card["via"] == "claude"
