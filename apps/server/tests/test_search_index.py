"""Meaning search in the app: background indexing and status."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from app.main import app
from brain_core.vectors import normalize

TOPICS = [("밸류업", "value-up"), ("자사주", "treasury"), ("환율", "exchange")]


class FakeEmbedder:
    model = "fake-embed"

    def __init__(self, ready=True):
        self.is_ready, self.batches = ready, 0

    def ready(self):
        return self.is_ready

    def _vec(self, text):
        low = text.lower()
        return [sum(low.count(w) for w in ws) + 0.01 for ws in TOPICS]

    def documents(self, texts):
        self.batches += 1
        return [self._vec(t) for t in texts]

    def query(self, q):
        return normalize(self._vec(q))


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.delenv("WOOJU_BRAIN_PATH", raising=False)
    with TestClient(app) as c:
        c.app.state.engine.embedder_override = FakeEmbedder()
        assert c.post("/api/setup/brain", json={"path": str(tmp_path / "B")}).status_code == 200
        b = tmp_path / "B"
        (b / "wiki/concepts/treasury.md").write_text(
            "---\ntitle: 자사주 소각\n---\n# 자사주 소각\n\n## 정의\n\n자사주는 1년 안에 소각해야 한다.\n",
            encoding="utf-8",
        )
        c.app.state.engine.index.scan(b)
        yield c


def wait_ready(c, timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = c.get("/api/search/status").json()
        if status["state"] == "ready":
            return status
        time.sleep(0.05)
    raise AssertionError(status)


def test_indexes_in_background_and_reports_progress(client):
    status = wait_ready(client)
    assert status["done"] == status["total"] > 0
    batches = client.app.state.engine.embedder_override.batches
    # Already up to date: nothing is embedded again.
    assert wait_ready(client) and client.app.state.engine.embedder_override.batches == batches


def test_off_without_the_model(client):
    client.app.state.engine.embedder_override = FakeEmbedder(ready=False)
    assert client.get("/api/search/status").json()["state"] == "off"


def _more_notes(c):
    b = c.app.state.engine.brain
    (b / "sources").mkdir(exist_ok=True)
    (b / "sources/treasury-law.md").write_text(
        "---\ntitle: Treasury shares must be cancelled\nsource_type: article\ncanonical_ref: x\n---\n"
        "# Treasury shares must be cancelled\n\n## Key Ideas\n\n- New treasury shares are cancelled within a year.\n",
        encoding="utf-8",
    )
    (b / "wiki/concepts/fx.md").write_text(
        "---\ntitle: 환율\n---\n# 환율\n\n## 정의\n\n원/달러 환율은 수출 기업 실적에 영향을 준다.\n"
        "\n## 관련\n\n- [자사주 소각](treasury.md)\n",
        encoding="utf-8",
    )
    c.app.state.engine.index.scan(b)
    c.get("/api/search/status")  # starts indexing the new notes
    wait_ready(c)
    deadline = time.time() + 5
    while time.time() < deadline and c.get("/api/search/status").json()["done"] < 3:
        time.sleep(0.05)


def test_search_page_finds_notes_by_meaning(client):
    _more_notes(client)
    body = client.get("/api/find", params={"q": "treasury"}).json()
    assert body["meaning"] is True
    ids = [h["id"] for h in body["hits"]]
    # The Korean note shares no word with the query and is found by meaning.
    assert "wiki/concepts/treasury" in ids and "sources/treasury-law" in ids
    assert len(ids) == len(set(ids))
    assert client.get("/api/find", params={"q": " "}).json()["total"] == 0


def test_related_shows_links_both_ways_and_similar_notes(client):
    _more_notes(client)
    rel = client.get("/api/related/wiki/concepts/treasury").json()
    assert [r["id"] for r in rel["links_in"]] == ["wiki/concepts/fx"]
    assert rel["links_out"] == []
    similar = {r["id"]: r for r in rel["similar"]}
    assert "sources/treasury-law" in similar and "wiki/concepts/fx" not in similar
    assert similar["sources/treasury-law"]["duplicate"] is True
    assert client.get("/api/related/nope").status_code == 404


def test_a_new_note_close_to_an_old_one_is_flagged_not_merged(client):
    import asyncio

    _more_notes(client)
    engine = client.app.state.engine
    near = asyncio.run(engine.near_duplicates("sources/treasury-law"))
    assert near == [{"id": "wiki/concepts/treasury", "title": "자사주 소각"}]
    # Both notes are still there.
    assert engine.index.get("sources/treasury-law") and engine.index.get("wiki/concepts/treasury")
