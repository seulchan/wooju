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
