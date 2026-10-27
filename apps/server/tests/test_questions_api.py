"""The AI asks; the user answers; the answer stays in the user's note."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from wooju_agents.llm import LLMResult


class Asker:
    name, model = "fake", "fake"

    def generate_json(self, system, user, schema):
        data = {
            "questions": [
                {"kind": "why", "text": "왜 그럴까?"},
                {"kind": "connect", "text": "습관과 어떻게 이어질까?", "other": 1},
            ]
        }
        return LLMResult(data, "", 0, self.name, self.model)


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.delenv("WOOJU_BRAIN_PATH", raising=False)
    monkeypatch.setenv("WOOJU_LANGUAGE", "ko")
    with TestClient(app) as c:
        c.app.state.engine.provider_override = Asker()
        assert c.post("/api/setup/brain", json={"path": str(tmp_path / "B")}).status_code == 200
        b = tmp_path / "B"
        cfg = b / "wooju-brain.yaml"
        cfg.write_text(cfg.read_text().replace("language: auto", "language: ko"), encoding="utf-8")
        for slug, title, body in [
            ("compound", "복리", "## 무엇인가\n\n이자에 이자가 붙는다. 시간이 길수록 커진다."),
            ("habit", "습관", "## 무엇인가\n\n작은 행동이 반복되며 시간이 길수록 커진다."),
        ]:
            (b / "wiki/concepts" / f"{slug}.md").write_text(
                f"---\ntitle: {title}\n---\n# {title}\n\n{body}\n", encoding="utf-8"
            )
        c.app.state.engine.index.scan(b)
        yield c, b


def test_questions_point_at_real_notes(client):
    c, _ = client
    r = c.post("/api/notes/questions", json={"id": "wiki/concepts/compound"})
    assert r.status_code == 200, r.text
    qs = r.json()["questions"]
    assert qs[0] == {"kind": "why", "text": "왜 그럴까?", "related": None}
    assert qs[1]["related"]["id"] == "wiki/concepts/habit"


def test_answers_accumulate_in_one_section(client):
    c, b = client
    for q, a in [
        ("왜 그럴까?", "시간이 지날수록 기반이 커져서."),
        ("한계는?", "중간에 손실이 크면 깨진다."),
    ]:
        r = c.post(
            "/api/notes/reflect", json={"id": "wiki/concepts/compound", "question": q, "answer": a}
        )
        assert r.status_code == 200
    text = (b / "wiki/concepts/compound.md").read_text(encoding="utf-8")
    assert text.count("## 생각해 본 것") == 1
    assert "- **왜 그럴까?**" in text and "기반이 커져서." in text and "손실이 크면 깨진다." in text
    assert c.get("/api/history").json()["items"][0]["title"] == "생각해 봄: 복리"


def test_empty_answer_is_refused(client):
    c, _ = client
    r = c.post(
        "/api/notes/reflect", json={"id": "wiki/concepts/compound", "question": "q", "answer": " "}
    )
    assert r.status_code == 400
