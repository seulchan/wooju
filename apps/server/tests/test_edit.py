"""Fixing notes: the user's own edits, and fixing a proposal before approving it."""

from __future__ import annotations

import pytest
from fake_ai import cited
from fastapi.testclient import TestClient

from app.main import app
from wooju_agents.llm import LLMResult

NOTE = """---
title: 환율
review_after: 2027-01-01
---
# 환율

## 정의

원/달러 환율은 수출 기업 실적에 영향을 준다.
"""
DRAFT = {
    "title": "Korea Value-up Index launch",
    "source_type": "article",
    "authors": [],
    "published": "2024-09-24",
    "one_line_summary": "100 stocks.",
    "key_points": ["67 on Kospi"],
    "limitations": [],
}


class Fake:
    name, model = "fake", "fake"

    def generate_json(self, system, user, schema):
        return LLMResult(cited(DRAFT, user, schema), "", 0.0, self.name, self.model)


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.delenv("WOOJU_BRAIN_PATH", raising=False)
    monkeypatch.setenv("WOOJU_LANGUAGE", "ko")
    with TestClient(app) as c:
        c.app.state.engine.provider_override = Fake()
        assert c.post("/api/setup/brain", json={"path": str(tmp_path / "B")}).status_code == 200
        b = tmp_path / "B"
        (b / "wiki/concepts/fx.md").write_text(NOTE, encoding="utf-8")
        c.app.state.engine.index.scan(b)
        yield c, b


def test_edit_a_note_keeps_frontmatter_and_can_be_undone(client):
    c, b = client
    base = c.get("/api/records/wiki/concepts/fx").json()["content"]
    new = base.replace("영향을 준다.", "영향을 준다. 환율이 오르면 수출 기업에 유리하다.")
    r = c.post("/api/notes/edit", json={"id": "wiki/concepts/fx", "body": new, "base": base})
    assert r.status_code == 200, r.text
    text = (b / "wiki/concepts/fx.md").read_text(encoding="utf-8")
    assert text.startswith("---\ntitle: 환율\nreview_after: 2027-01-01\n---\n")
    assert "수출 기업에 유리하다" in text
    top = c.get("/api/history").json()["items"][0]
    assert top["title"] == "직접 고침: 환율"
    assert c.post(f"/api/history/{top['id']}/undo").status_code == 200
    assert "유리하다" not in (b / "wiki/concepts/fx.md").read_text(encoding="utf-8")


def test_edit_refuses_to_overwrite_a_change_made_elsewhere(client):
    c, b = client
    base = c.get("/api/records/wiki/concepts/fx").json()["content"]
    (b / "wiki/concepts/fx.md").write_text(
        NOTE.replace("준다.", "준다. (다른 앱에서 고침)"), encoding="utf-8"
    )
    r = c.post(
        "/api/notes/edit", json={"id": "wiki/concepts/fx", "body": base + "\n추가", "base": base}
    )
    assert r.status_code == 409 and "바뀌었어요" in r.json()["detail"]
    assert "다른 앱에서 고침" in (b / "wiki/concepts/fx.md").read_text(encoding="utf-8")


def test_empty_edit_is_refused(client):
    c, _ = client
    base = c.get("/api/records/wiki/concepts/fx").json()["content"]
    r = c.post("/api/notes/edit", json={"id": "wiki/concepts/fx", "body": "  ", "base": base})
    assert r.status_code == 400


def test_fix_a_proposal_before_approving(client, monkeypatch):
    c, b = client
    from brain_core.changes import FileChange, Proposal

    engine = c.app.state.engine
    proposal = engine.store.save(
        Proposal(
            agent="claude",
            title="Claude: 환율 2",
            changes=[
                FileChange(
                    op="write", path="wiki/concepts/fx2.md", content=NOTE.replace("환율", "환율 2")
                )
            ],
            approval="batch",
        )
    )
    preview = c.get("/api/proposals", params={"status": "pending"}).json()["items"][0]["preview"]
    body = preview.split("---\n", 2)[2].replace("영향을 준다.", "영향을 크게 준다.")
    r = c.post(f"/api/proposals/{proposal.id}/edit", json={"body": body})
    assert r.status_code == 200 and "크게 준다" in r.json()["preview"]
    assert c.post(f"/api/proposals/{proposal.id}/approve").json()["status"] == "applied"
    saved = (b / "wiki/concepts/fx2.md").read_text(encoding="utf-8")
    assert saved.startswith("---\ntitle: 환율 2\n") and "크게 준다" in saved
