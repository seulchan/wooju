"""Retiring a wrong note: kept with its reason, never used as grounds, restorable."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from brain_core import history
from wooju_agents.llm import LLMResult

SOURCE = """---
title: 자사주 소각 해설
source_type: article
canonical_ref: https://example.com/a
status: active
---
# 자사주 소각 해설

## 핵심 내용

- 자사주는 1년 안에 소각해야 한다.
"""
INSIGHT = """---
title: 자사주 많은 기업의 재평가
origin: synthesis
insight_kind: hypothesis
status: candidate
derived_from:
  - "[해설](../../sources/treasury.md)"
---
# 자사주 많은 기업의 재평가

## Insight

자사주 소각 의무화로 재평가될 수 있다.
"""


class Scripted:
    name, model = "fake", "fake"

    def __init__(self):
        self.prompts = []

    def generate_json(self, system, user, schema):
        self.prompts.append(user)
        if "queries" in schema["properties"]:
            return LLMResult({"queries": ["자사주"]}, "", 0, self.name, self.model)
        data = {"statements": [{"text": "1년 안에 소각해요.", "sources": [1]}], "missing": ""}
        return LLMResult(data, "", 0, self.name, self.model)


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.delenv("WOOJU_BRAIN_PATH", raising=False)
    monkeypatch.setenv("WOOJU_LANGUAGE", "ko")
    with TestClient(app) as c:
        c.app.state.engine.provider_override = Scripted()
        assert c.post("/api/setup/brain", json={"path": str(tmp_path / "B")}).status_code == 200
        b = tmp_path / "B"
        (b / "wiki/questions").mkdir(parents=True, exist_ok=True)
        (b / "sources/treasury.md").write_text(SOURCE, encoding="utf-8")
        (b / "wiki/questions/rerating.md").write_text(INSIGHT, encoding="utf-8")
        history.commit_paths(b, ["sources/treasury.md", "wiki/questions/rerating.md"], "Add")
        c.app.state.engine.index.scan(b)
        yield c, b


def test_retire_keeps_the_note_and_stops_using_it(client):
    c, b = client
    r = c.post(
        "/api/notes/retire", json={"id": "sources/treasury", "reason": "정정 보도: 기한은 18개월"}
    )
    assert r.status_code == 200, r.text
    text = (b / "sources/treasury.md").read_text(encoding="utf-8")
    assert "retired: " in text and 'retired_reason: "정정 보도: 기한은 18개월"' in text
    assert "status: archived" in text and "status_before_retired: active" in text
    assert "1년 안에 소각해야 한다." in text  # what the source said is kept

    record = c.get("/api/records/sources/treasury").json()
    assert record["retired"] is True
    assert c.get("/api/sources").json()["items"][0]["retired"] is True

    # Not grounds for answers anymore.
    answer = c.post("/api/ask", json={"question": "자사주는 언제까지 소각해?"}).json()
    assert "sources/treasury" not in [x["id"] for x in answer["citations"]]
    prompt = c.app.state.engine.provider_override.prompts[-1]
    assert "1년 안에 소각해야 한다" not in prompt

    # What rested on it is flagged, marked as resting on a retired note.
    groups = {g["key"]: g for g in c.get("/api/attention").json()["groups"]}
    item = groups["grounds_changed"]["items"][0]
    assert item["id"] == "wiki/questions/rerating" and item["detail"] == "⊘ 자사주 소각 해설"
    assert c.get("/api/history").json()["items"][0]["title"] == "폐기: 자사주 소각 해설"


def test_restore_brings_back_the_old_status(client):
    c, b = client
    c.post("/api/notes/retire", json={"id": "sources/treasury", "reason": "착각"})
    assert c.post("/api/notes/restore", json={"id": "sources/treasury"}).status_code == 200
    text = (b / "sources/treasury.md").read_text(encoding="utf-8")
    assert "retired" not in text and "status: active" in text
    assert c.get("/api/records/sources/treasury").json()["retired"] is False


def test_retire_an_insight_rejects_it(client):
    c, b = client
    c.post("/api/notes/retire", json={"id": "wiki/questions/rerating", "reason": "근거 부족"})
    text = (b / "wiki/questions/rerating.md").read_text(encoding="utf-8")
    assert "status: rejected" in text and "status_before_retired: candidate" in text


def test_reason_is_required(client):
    c, _ = client
    r = c.post("/api/notes/retire", json={"id": "sources/treasury", "reason": " "})
    assert r.status_code == 400 and "이유" in r.json()["detail"]
