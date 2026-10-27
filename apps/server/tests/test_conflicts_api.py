"""A new source that disagrees with an existing note is flagged, not changed."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from app.main import app
from brain_core import history
from wooju_agents.llm import LLMResult

OLD = """---
title: 자사주 소각 해설
source_type: article
canonical_ref: https://example.com/old
---
# 자사주 소각 해설

## 핵심 내용

- 자사주는 1년 안에 소각해야 한다.
"""
DRAFT = {
    "title": "자사주 소각 기한 정정",
    "source_type": "article",
    "authors": [],
    "published": "2026-10-01",
    "one_line_summary": "자사주는 18개월 안에 소각해야 한다.",
    "key_points": ["자사주 소각 기한은 18개월이다."],
    "limitations": [],
}
TEXT = ("자사주 소각 기한은 18개월로 정정됐다. 자사주 소각 의무화 관련 보도. " * 5).encode()


class Scripted:
    name, model = "fake", "fake"

    def generate_json(self, system, user, schema):
        if "conflicts" in schema["properties"]:
            data = {
                "conflicts": [
                    {
                        "new_claim": "18개월 안에 소각",
                        "existing": 1,
                        "existing_claim": "1년 안에 소각",
                    }
                ]
            }
        else:
            data = DRAFT
        return LLMResult(data, "", 0, self.name, self.model)


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.delenv("WOOJU_BRAIN_PATH", raising=False)
    monkeypatch.setenv("WOOJU_LANGUAGE", "ko")
    with TestClient(app) as c:
        c.app.state.engine.provider_override = Scripted()
        assert c.post("/api/setup/brain", json={"path": str(tmp_path / "B")}).status_code == 200
        b = tmp_path / "B"
        (b / "sources/old.md").write_text(OLD, encoding="utf-8")
        history.commit_paths(b, ["sources/old.md"], "Add")
        c.app.state.engine.index.scan(b)
        yield c, b


def wait_jobs(c):
    deadline = time.time() + 10
    while time.time() < deadline:
        items = c.get("/api/jobs").json()["items"]
        if items and all(j["state"] in ("done", "failed") for j in items):
            return items
        time.sleep(0.05)
    raise AssertionError(items)


def test_new_source_conflict_is_written_and_shown(client):
    c, b = client
    c.post("/api/inbox", files=[("files", ("correction.txt", TEXT, "text/plain"))])
    job = wait_jobs(c)[0]
    assert job["state"] == "done" and job["conflicts"] == 1
    assert "1건" in job["message"]
    new = next(p for p in (b / "sources").glob("*.md") if p.name != "old.md")
    text = new.read_text(encoding="utf-8")
    assert "## Conflicts" in text and "[자사주 소각 해설](old.md)" in text
    assert (b / "sources/old.md").read_text(encoding="utf-8") == OLD  # never changed

    groups = {g["key"]: g for g in c.get("/api/attention").json()["groups"]}
    item = groups["conflicts"]["items"][0]
    assert item["id"] == f"sources/{new.stem}" and "18개월" in item["detail"]

    assert c.post("/api/checked", json={"id": item["id"], "kind": "conflict"}).status_code == 200
    groups = {g["key"]: g for g in c.get("/api/attention").json()["groups"]}
    assert "conflicts" not in groups
