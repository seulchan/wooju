"""The topics agent end to end, with hand-made vectors standing in for a model."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from app.main import app
from brain_core.markdown import split_frontmatter
from brain_core.vectors import normalize
from wooju_agents.llm import LLMResult

TOPICS = [("금리", "rate"), ("자사주", "treasury"), ("환율", "exchange")]


class FakeEmbedder:
    model = "fake-embed"

    def ready(self):
        return True

    def _vec(self, text):
        low = text.lower()
        return [sum(low.count(w) for w in ws) + 0.01 for ws in TOPICS]

    def documents(self, texts):
        return [self._vec(t) for t in texts]

    def query(self, q):
        return normalize(self._vec(q))


class Writer:
    name, model = "fake", "fake-1"

    def generate_json(self, system, user, schema):
        return LLMResult(
            {
                "title": "환율",
                "summary": [{"text": "환율이 수출 실적을 흔든다.", "sources": [1, 2]}],
            },
            "",
            0.1,
            self.name,
            self.model,
        )


def source(title, word):
    return (
        f"---\ntitle: {title}\nsource_type: article\ncanonical_ref: x\n---\n# {title}\n\n"
        f"## 핵심 내용\n\n- {word} {word} {word}\n"
    )


TOPIC = """---
title: 기준금리
---
# 기준금리

사용자가 쓴 지도. [첫 인상](../../sources/rate-1.md), [두 번째](../../sources/rate-2.md)
"""


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.delenv("WOOJU_BRAIN_PATH", raising=False)
    monkeypatch.setenv("WOOJU_LANGUAGE", "ko")
    with TestClient(app) as c:
        engine = c.app.state.engine
        engine.embedder_override = FakeEmbedder()
        engine.provider_override = Writer()
        assert c.post("/api/setup/brain", json={"path": str(tmp_path / "B")}).status_code == 200
        b = tmp_path / "B"
        (b / "wiki/overviews").mkdir(parents=True, exist_ok=True)
        (b / "wiki/overviews/rates.md").write_text(TOPIC, encoding="utf-8")
        files = {
            "sources/rate-1.md": source("첫 인상", "금리"),
            "sources/rate-2.md": source("두 번째 인상", "금리"),
            "sources/rate-3.md": source("세 번째 금리 기사", "금리"),
        }
        for i in range(4):
            files[f"sources/fx-{i}.md"] = source(f"환율 기사 {i}", "환율")
        for rel, text in files.items():
            (b / rel).write_text(text, encoding="utf-8")
        engine.index.scan(b)
        yield c, b


def settle(c, timeout=8):
    """Index vectors and let the topics agent file notes."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        c.get("/api/search/status")
        engine = c.app.state.engine
        if (
            engine.search_state.get("state") == "ready"
            and engine._swept_at == engine.index.indexed_at
        ):
            return
        time.sleep(0.05)
    raise AssertionError(c.app.state.engine.search_state)


def test_a_loose_note_is_filed_into_its_topic_and_the_body_is_kept(client):
    c, b = client
    settle(c)
    text = (b / "wiki/overviews/rates.md").read_text(encoding="utf-8")
    assert "사용자가 쓴 지도." in text
    assert "## 이 주제의 노트\n\n- [세 번째 금리 기사](../../sources/rate-3.md)" in text
    fm = split_frontmatter(text)[0]
    assert fm["topic_notes"] == ["sources/rate-3.md"]
    assert fm["made_by"][-1]["did"] == "topic link"
    # FX notes are not about rates.
    assert "fx-" not in text

    view = c.get("/api/topics/view/wiki/overviews/rates").json()
    members = {m["id"]: m for m in view["members"]}
    assert members["sources/rate-3"]["by_agent"] is True
    assert members["sources/rate-1"]["by_agent"] is False
    topics = c.get("/api/topics").json()["items"]
    assert topics == [{"id": "wiki/overviews/rates", "title": "기준금리", "count": 3}]


def test_a_note_taken_out_stays_out(client):
    c, b = client
    settle(c)
    r = c.post(
        "/api/topics/remove", json={"topic": "wiki/overviews/rates", "member": "sources/rate-3"}
    )
    assert r.status_code == 200, r.text
    c.app.state.engine._swept_at = None
    settle(c)
    text = (b / "wiki/overviews/rates.md").read_text(encoding="utf-8")
    assert "rate-3" not in text.split("---", 2)[2]
    assert split_frontmatter(text)[0]["topic_excluded"] == ["sources/rate-3.md"]
    # Put back by hand: allowed again.
    assert c.post(
        "/api/topics/add", json={"topic": "wiki/overviews/rates", "member": "sources/rate-3"}
    ).json() == {"added": True}
    assert "sources/rate-3.md" not in split_frontmatter(
        (b / "wiki/overviews/rates.md").read_text("utf-8")
    )[0].get("topic_excluded", [])


def test_a_group_of_close_notes_is_suggested_then_created_or_dismissed(client):
    c, b = client
    settle(c)
    items = c.get("/api/topics/suggestions").json()["items"]
    assert len(items) == 1
    members = [m["id"] for m in items[0]["members"]]
    assert sorted(members) == [f"sources/fx-{i}" for i in range(4)]

    r = c.post("/api/topics/create", json={"members": members})
    assert r.status_code == 200, r.text
    created = [p for p in (b / "wiki/overviews").glob("*.md") if p.name != "rates.md"]
    assert len(created) == 1
    text = created[0].read_text(encoding="utf-8")
    assert "# 환율" in text and "환율이 수출 실적을 흔든다." in text
    assert text.count("](../../sources/fx-") >= 4
    assert c.get("/api/topics/suggestions").json()["items"] == []


def test_a_dismissed_suggestion_does_not_come_back(client):
    c, _ = client
    settle(c)
    members = [m["id"] for m in c.get("/api/topics/suggestions").json()["items"][0]["members"]]
    assert c.post("/api/topics/dismiss", json={"members": members}).json() == {"ok": True}
    assert c.get("/api/topics/suggestions").json()["items"] == []
