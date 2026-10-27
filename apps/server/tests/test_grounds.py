"""When a note's grounds change, the note is surfaced to check again (never rewritten)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from brain_core import history

SOURCE = """---
title: 자사주 소각 해설
source_type: article
canonical_ref: https://example.com/a
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
KNOWLEDGE = """---
title: 자사주 소각
---
# 자사주 소각

## 정의

[[sources/treasury]]에 따르면 1년 안에 소각해야 한다.
"""


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.delenv("WOOJU_BRAIN_PATH", raising=False)
    monkeypatch.setenv("WOOJU_LANGUAGE", "en")
    with TestClient(app) as c:
        assert c.post("/api/setup/brain", json={"path": str(tmp_path / "B")}).status_code == 200
        b = tmp_path / "B"
        (b / "wiki/questions").mkdir(parents=True, exist_ok=True)
        (b / "sources/treasury.md").write_text(SOURCE, encoding="utf-8")
        (b / "wiki/questions/rerating.md").write_text(INSIGHT, encoding="utf-8")
        (b / "wiki/concepts/treasury.md").write_text(KNOWLEDGE, encoding="utf-8")
        history.commit_paths(
            b,
            ["sources/treasury.md", "wiki/questions/rerating.md", "wiki/concepts/treasury.md"],
            "Add notes",
        )
        c.app.state.engine.index.scan(b)
        yield c, b


def flagged(c):
    groups = {g["key"]: g for g in c.get("/api/attention").json()["groups"]}
    group = groups.get("grounds_changed")
    return {i["id"]: i["detail"] for i in group["items"]} if group else {}


def test_notes_added_together_are_not_flagged(client):
    c, _ = client
    assert flagged(c) == {}


def test_editing_a_source_flags_what_rests_on_it(client):
    c, b = client
    deps = c.get("/api/dependents/sources/treasury").json()["items"]
    assert {d["id"] for d in deps} == {"wiki/questions/rerating", "wiki/concepts/treasury"}

    base = c.get("/api/records/sources/treasury").json()["content"]
    c.post(
        "/api/notes/edit",
        json={"id": "sources/treasury", "body": base.replace("1년", "18개월"), "base": base},
    )
    assert flagged(c) == {
        "wiki/questions/rerating": "자사주 소각 해설",
        "wiki/concepts/treasury": "자사주 소각 해설",
    }
    # Nothing was rewritten.
    assert (b / "wiki/questions/rerating.md").read_text(encoding="utf-8") == INSIGHT

    # Checked → gone; editing the note itself also clears it.
    assert c.post("/api/checked", json={"id": "wiki/questions/rerating"}).status_code == 200
    base = c.get("/api/records/wiki/concepts/treasury").json()["content"]
    c.post(
        "/api/notes/edit",
        json={"id": "wiki/concepts/treasury", "body": base.replace("1년", "18개월"), "base": base},
    )
    assert flagged(c) == {}


def test_a_later_change_flags_it_again(client):
    c, _ = client
    for text in ("18개월", "2년"):
        base = c.get("/api/records/sources/treasury").json()["content"]
        c.post(
            "/api/notes/edit",
            json={
                "id": "sources/treasury",
                "body": base.replace("1년", text).replace("18개월", text),
                "base": base,
            },
        )
        if text == "18개월":
            c.post("/api/checked", json={"id": "wiki/questions/rerating"})
            assert "wiki/questions/rerating" not in flagged(c)
    assert "wiki/questions/rerating" in flagged(c)
