"""Writing in Wooju: new notes, thoughts with grounds, and one-line takeaways."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from app.main import app
from brain_core.validate import validate_brain
from wooju_agents.llm import LLMResult

DRAFT = {
    "title": "Korea Value-up Index launch",
    "source_type": "article",
    "authors": [],
    "published": "2024-09-24",
    "one_line_summary": "100 stocks.",
    "key_points": ["67 on Kospi"],
    "limitations": [],
}
TEXT = b"Korea Value-up Index to begin publication next week. 100 stocks, 67 on Kospi and 33 on Kosdaq."


class Fake:
    name, model = "fake", "fake"

    def generate_json(self, system, user, schema):
        return LLMResult(DRAFT, "", 0, self.name, self.model)


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.delenv("WOOJU_BRAIN_PATH", raising=False)
    monkeypatch.setenv("WOOJU_LANGUAGE", "ko")
    with TestClient(app) as c:
        c.app.state.engine.provider_override = Fake()
        assert c.post("/api/setup/brain", json={"path": str(tmp_path / "B")}).status_code == 200
        b = tmp_path / "B"
        cfg = b / "wooju-brain.yaml"
        cfg.write_text(cfg.read_text().replace("language: auto", "language: ko"), encoding="utf-8")
        yield c, b


def test_skeleton_follows_the_brain_language(client):
    c, _ = client
    body = c.get("/api/notes/skeleton", params={"kind": "concept"}).json()["body"]
    assert body.startswith("## 무엇인가")
    assert (
        c.get("/api/notes/skeleton", params={"kind": "thought"})
        .json()["body"]
        .startswith("## Insight")
    )


def test_new_concept_note(client):
    c, b = client
    r = c.post(
        "/api/notes/new",
        json={"kind": "concept", "title": "복리", "body": "## 무엇인가\n\n이자에 이자가 붙는 것."},
    )
    assert r.status_code == 200, r.text
    note_id = r.json()["id"]
    assert note_id.startswith("wiki/concepts/concept-")
    text = (b / f"{note_id}.md").read_text(encoding="utf-8")
    assert text.startswith("---\ntitle: 복리\n---\n# 복리\n\n## 무엇인가")
    record = c.get(f"/api/records/{note_id}").json()
    assert record["title"] == "복리" and record["category"] == "knowledge"
    assert c.get("/api/history").json()["items"][0]["title"] == "새 노트: 복리"


def test_english_title_names_the_file(client):
    c, _ = client
    r = c.post("/api/notes/new", json={"kind": "how-to", "title": "Read an annual report"})
    assert r.json()["id"] == "wiki/how-tos/read-an-annual-report"


def test_thought_needs_grounds_and_becomes_a_candidate_insight(client):
    c, b = client
    r = c.post(
        "/api/notes/new", json={"kind": "thought", "title": "생각", "body": "## Insight\n\n가설"}
    )
    assert r.status_code == 400 and "근거" in r.json()["detail"]

    c.post("/api/notes/new", json={"kind": "concept", "title": "Compound interest", "body": "x"})
    r = c.post(
        "/api/notes/new",
        json={
            "kind": "thought",
            "title": "작은 습관도 복리처럼 쌓인다",
            "body": "## Insight\n\n습관의 효과는 시간이 지날수록 커진다.",
            "grounds": ["wiki/concepts/compound-interest"],
            "insight_kind": "connection",
        },
    )
    assert r.status_code == 200, r.text
    record = c.get(f"/api/records/{r.json()['id']}").json()
    assert record["category"] == "insight" and record["status"] == "candidate"
    assert record["kind"] == "connection"
    assert record["derived_from_resolved"][0]["resolved_id"] == "wiki/concepts/compound-interest"
    assert not [e for e in validate_brain(b).errors if "wiki/" in e.path]


def test_takeaway_after_a_source_is_saved(client):
    c, b = client
    c.post("/api/inbox", files=[("files", ("value-up.txt", TEXT, "text/plain"))])
    deadline = time.time() + 10
    while time.time() < deadline:
        jobs = c.get("/api/jobs").json()["items"]
        if jobs and jobs[0]["state"] == "done":
            break
        time.sleep(0.05)
    note_id = jobs[0]["note_id"]
    assert note_id == "sources/korea-value-up-index-launch"

    r = c.post(
        "/api/notes/takeaway", json={"id": note_id, "text": "지수 편입이 곧 재평가는 아니다."}
    )
    assert r.status_code == 200
    text = (b / f"{note_id}.md").read_text(encoding="utf-8")
    assert text.index("## 내 생각") < text.index("## 원본")
    # Saving again replaces the line instead of adding a second section.
    c.post("/api/notes/takeaway", json={"id": note_id, "text": "두 번째 생각"})
    text = (b / f"{note_id}.md").read_text(encoding="utf-8")
    assert (
        text.count("## 내 생각") == 1 and "두 번째 생각" in text and "재평가는 아니다" not in text
    )
