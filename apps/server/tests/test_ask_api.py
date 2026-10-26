"""Ask and Challenger over HTTP, with a real Brain and a scripted AI."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from wooju_agents.llm import LLMError, LLMResult

INSIGHT = """---
title: 자사주 많은 기업의 재평가
origin: synthesis
insight_kind: hypothesis
status: candidate
derived_from:
  - "[[concepts/treasury]]"
---
# 자사주 많은 기업의 재평가

## Insight

자사주 소각 의무화로 자사주가 많은 기업이 재평가될 수 있다.
"""


class Scripted:
    name, model = "fake", "fake-1"

    def __init__(self, fail: LLMError | None = None):
        self.fail = fail

    def generate_json(self, system, user, schema):
        if self.fail:
            raise self.fail
        props = schema["properties"]
        if "queries" in props:
            data = {"queries": ["자사주"]}
        elif "verdict" in props:
            data = {
                "wrong_if": ["주총 승인으로 보유가 허용되면 [1]"],
                "restatement": False,
                "verdict": "refine",
                "reason": "범위를 좁혀야 한다.",
            }
        else:
            data = {
                "statements": [{"text": "1년 안에 소각해야 해요.", "sources": [1]}],
                "missing": "",
            }
        return LLMResult(data, "", 0.2, self.name, self.model)


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.delenv("WOOJU_BRAIN_PATH", raising=False)
    monkeypatch.setenv("WOOJU_LANGUAGE", "ko")
    with TestClient(app) as c:
        c.app.state.engine.provider_override = Scripted()
        r = c.post("/api/setup/brain", json={"path": str(tmp_path / "B")})
        assert r.status_code == 200
        brain = tmp_path / "B"
        (brain / "wiki/concepts/treasury.md").write_text(
            "---\ntitle: 자사주 소각\n---\n# 자사주 소각\n\n## 정의\n\n자사주는 1년 안에 소각해야 한다.\n",
            encoding="utf-8",
        )
        (brain / "wiki/questions").mkdir(parents=True, exist_ok=True)
        (brain / "wiki/questions/rerating.md").write_text(INSIGHT, encoding="utf-8")
        c.app.state.engine.index.scan(brain)
        yield c


def test_ask_returns_cited_answer(client):
    r = client.post("/api/ask", json={"question": "자사주는 언제까지 소각해야 해?"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["found"] is True
    assert body["answer"] == "1년 안에 소각해야 해요. [1]"
    assert body["citations"][0]["id"] == "wiki/concepts/treasury"
    assert body["citations"][0]["title"] == "자사주 소각"


def test_ask_empty_question(client):
    r = client.post("/api/ask", json={"question": " "})
    assert r.status_code == 400 and "질문" in r.json()["detail"]


def test_ask_when_ai_is_not_ready(client):
    client.app.state.engine.provider_override = Scripted(
        LLMError("off", "llm.ollama_off", retryable=True)
    )
    r = client.post("/api/ask", json={"question": "자사주 소각 기한"})
    assert r.status_code == 503 and "Ollama" in r.json()["detail"]


def test_challenge_creates_a_pending_proposal(client):
    r = client.post("/api/challenge", json={"id": "wiki/questions/rerating"})
    assert r.status_code == 200, r.text
    view = r.json()
    assert view["status"] == "pending" and view["agent"] == "challenger"
    assert view["summary"].startswith("보완 필요")
    pending = client.get("/api/proposals", params={"status": "pending"}).json()["items"]
    assert any(p["id"] == view["id"] for p in pending)

    r = client.post(f"/api/proposals/{view['id']}/approve")
    assert r.status_code == 200 and r.json()["status"] == "applied"
    record = client.get("/api/records/wiki/questions/rerating").json()
    assert "## Challenge" in record["content"]


def test_challenge_rejects_non_insights(client):
    r = client.post("/api/challenge", json={"id": "wiki/concepts/treasury"})
    assert r.status_code == 400
    r = client.post("/api/challenge", json={"id": "wiki/nope"})
    assert r.status_code == 404
