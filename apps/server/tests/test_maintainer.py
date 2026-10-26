"""The Maintainer: notes due for review, notes that break the rules, and 'reviewed'."""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.projections.attention import compute_attention
from brain_core.index import BrainIndex

DUE = """---
title: 삼성전자 실적 가설
review_after: 2026-07-31
---
# 삼성전자 실적 가설

## Thesis

다음 실적 발표에서 HBM 매출 비중을 다시 확인한다.
"""

LATER = """---
title: 환율 메모
review_after: 2099-01-01
---
# 환율 메모

본문.
"""

BROKEN = """---
title: 깨진 자료
source_type: news
canonical_ref: x
---
# 깨진 자료

본문.
"""


@pytest.fixture
def brain(tmp_path):
    (tmp_path / "wiki" / "overviews").mkdir(parents=True)
    (tmp_path / "sources").mkdir()
    (tmp_path / "wiki" / "overviews" / "samsung.md").write_text(DUE, encoding="utf-8")
    (tmp_path / "wiki" / "overviews" / "fx.md").write_text(LATER, encoding="utf-8")
    (tmp_path / "sources" / "broken.md").write_text(BROKEN, encoding="utf-8")
    return tmp_path


def test_due_and_rule_errors_are_surfaced(brain):
    index = BrainIndex()
    index.scan(brain)
    result = compute_attention(index, today=date(2026, 10, 27), brain=brain)
    groups = {g.key: g for g in result.groups}
    assert [i.id for i in groups["review_due"].items] == ["wiki/overviews/samsung"]
    assert groups["review_due"].items[0].detail == "2026-07-31"
    assert [i.id for i in groups["rule_errors"].items] == ["sources/broken"]
    assert "source_type" in (groups["rule_errors"].items[0].detail or "")
    assert result.groups[0].key == "review_due"  # shown first


def test_not_due_yet(brain):
    index = BrainIndex()
    index.scan(brain)
    result = compute_attention(index, today=date(2026, 7, 30), brain=brain)
    assert "review_due" not in {g.key for g in result.groups}


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.delenv("WOOJU_BRAIN_PATH", raising=False)
    monkeypatch.setenv("WOOJU_LANGUAGE", "ko")
    with TestClient(app) as c:
        assert c.post("/api/setup/brain", json={"path": str(tmp_path / "B")}).status_code == 200
        b = tmp_path / "B"
        (b / "wiki/overviews").mkdir(parents=True, exist_ok=True)
        (b / "wiki/overviews/samsung.md").write_text(DUE, encoding="utf-8")
        c.app.state.engine.index.scan(b)
        yield c, b


def test_mark_reviewed_moves_the_date_and_can_be_undone(client):
    c, b = client
    assert any(g["key"] == "review_due" for g in c.get("/api/attention").json()["groups"])

    r = c.post("/api/review-date", json={"id": "wiki/overviews/samsung", "until": "2027-01-31"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "applied"
    text = (b / "wiki/overviews/samsung.md").read_text(encoding="utf-8")
    assert "review_after: 2027-01-31" in text and "HBM" in text
    assert not any(g["key"] == "review_due" for g in c.get("/api/attention").json()["groups"])

    top = c.get("/api/history").json()["items"][0]
    assert top["title"].startswith("검토함, 다음 검토 2027-01-31")
    assert c.post(f"/api/history/{top['id']}/undo").status_code == 200
    assert "review_after: 2026-07-31" in (b / "wiki/overviews/samsung.md").read_text(
        encoding="utf-8"
    )


def test_clear_review_date(client):
    c, b = client
    r = c.post("/api/review-date", json={"id": "wiki/overviews/samsung", "until": None})
    assert r.status_code == 200
    assert "review_after" not in (b / "wiki/overviews/samsung.md").read_text(encoding="utf-8")


def test_unknown_note(client):
    c, _ = client
    r = c.post("/api/review-date", json={"id": "wiki/nope", "until": "2027-01-01"})
    assert r.status_code == 404
