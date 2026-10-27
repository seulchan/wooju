"""Only one AI task runs at a time: organizing, indexing, answering, challenging."""

from __future__ import annotations

import threading
import time

import pytest
from fastapi.testclient import TestClient

from app.main import app
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
TEXT = ("Korea Value-up Index to begin publication next week. 100 stocks. " * 10).encode()


class SlowProvider:
    """Takes a while per call and records how many calls overlap."""

    name, model = "fake", "fake"

    def __init__(self):
        self.running = 0
        self.most = 0
        self.guard = threading.Lock()

    def generate_json(self, system, user, schema):
        with self.guard:
            self.running += 1
            self.most = max(self.most, self.running)
        time.sleep(0.3)
        with self.guard:
            self.running -= 1
        props = schema["properties"]
        if "statements" in props:
            data = {"statements": [{"text": "100개예요.", "sources": [1]}], "missing": ""}
        elif "queries" in props:
            data = {"queries": ["value-up"]}
        else:
            data = DRAFT
        return LLMResult(data, "", 0.3, self.name, self.model)


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.delenv("WOOJU_BRAIN_PATH", raising=False)
    with TestClient(app) as c:
        assert c.post("/api/setup/brain", json={"path": str(tmp_path / "B")}).status_code == 200
        yield c


def test_asking_while_files_are_organized_never_overlaps(client):
    provider = SlowProvider()
    client.app.state.engine.provider_override = provider
    client.post(
        "/api/inbox",
        files=[("files", (f"value-up-{n}.txt", TEXT, "text/plain")) for n in range(2)],
    )
    time.sleep(0.1)  # the first file is being organized
    r = client.post("/api/ask", json={"question": "Korea Value-up Index stocks?"})
    assert r.status_code == 200, r.text
    deadline = time.time() + 10
    while time.time() < deadline:
        items = client.get("/api/jobs").json()["items"]
        if all(j["state"] in ("done", "failed") for j in items):
            break
        time.sleep(0.05)
    assert provider.most == 1


def test_memo_is_saved_at_once_while_a_file_is_organized(client):
    provider = SlowProvider()
    client.app.state.engine.provider_override = provider
    client.post("/api/inbox", files=[("files", ("value-up.txt", TEXT, "text/plain"))])
    time.sleep(0.05)
    start = time.time()
    r = client.post("/api/capture", json={"text": "HBM 비중 다시 볼 것"})
    assert r.status_code == 200 and r.json()["kind"] == "memo"
    assert time.time() - start < 0.3  # did not wait for the AI
