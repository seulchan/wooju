"""First-run setup, adding files, approvals, and undo, end to end.

The AI is a fake provider; everything else (template copy, git, validator,
index) is real.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from app import settings as app_settings
from app.main import app
from brain_core.changes import FileChange, Proposal
from wooju_agents.llm import LLMResult

DRAFT = {
    "title": "Korea Value-up Index launch",
    "source_type": "article",
    "authors": ["Korea JoongAng Daily"],
    "published": "2024-09-24",
    "one_line_summary": "밸류업 지수는 2024 년 9 월 30 일부터 100 개 종목으로 산출된다.",
    "key_points": ["코스피 67 개, 코스닥 33 개"],
    "limitations": ["방법론 원문은 확인하지 않았다."],
}
TEXT = b"Korea Value-up Index to begin publication next week. 100 stocks, 67 on Kospi and 33 on Kosdaq."


class FakeProvider:
    name, model = "fake", "fake"

    def __init__(self, data=DRAFT):
        self.data = data

    def generate_json(self, system, user, schema):
        return LLMResult(self.data, "", 0.0, self.name, self.model)


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.delenv("WOOJU_BRAIN_PATH", raising=False)
    monkeypatch.setenv("WOOJU_LANGUAGE", "ko")
    with TestClient(app) as c:
        c.app.state.engine.provider_override = FakeProvider()
        yield c


def wait_jobs(client, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        items = client.get("/api/jobs").json()["items"]
        if items and all(j["state"] in ("done", "failed") for j in items):
            return items
        time.sleep(0.05)
    raise AssertionError(f"jobs did not finish: {items}")


def setup_brain(client, tmp_path):
    r = client.post("/api/setup/brain", json={"path": str(tmp_path / "My Brain")})
    assert r.status_code == 200, r.text
    return tmp_path / "My Brain"


def test_first_run_creates_brain_from_template(client, tmp_path):
    status = client.get("/api/setup").json()
    assert status["brain_ready"] is False and status["brain_path"] is None
    assert status["ai"]["provider"] == "ollama"

    brain = setup_brain(client, tmp_path)
    assert (brain / "AGENTS.md").is_file() and (brain / "wiki/concepts").is_dir()
    assert (brain / ".git").is_dir()
    assert app_settings.load().brain_path == str(brain.resolve())
    assert client.get("/api/setup").json()["brain_ready"] is True
    assert client.get("/api/history").json()["items"][0]["title"] == "Start this Brain"

    # Choosing it again opens it instead of copying over it.
    again = client.post("/api/setup/brain", json={"path": str(brain)}).json()
    assert again["created"] is False


def test_refuses_a_folder_with_other_files(client, tmp_path):
    busy = tmp_path / "busy"
    busy.mkdir()
    (busy / "taxes.xlsx").write_text("x")
    r = client.post("/api/setup/brain", json={"path": str(busy)})
    assert r.status_code == 400 and "빈 폴더" in r.json()["detail"]
    assert not (busy / "AGENTS.md").exists()


def test_upload_needs_a_brain_first(client):
    r = client.post("/api/inbox", files=[("files", ("a.txt", TEXT, "text/plain"))])
    assert r.status_code == 400 and "폴더" in r.json()["detail"]


def test_drop_a_file_and_it_is_saved_as_a_source(client, tmp_path):
    brain = setup_brain(client, tmp_path)
    r = client.post(
        "/api/inbox",
        files=[
            ("files", ("value-up.txt", TEXT, "text/plain")),
            ("files", ("photo.heic", b"x", "image/heic")),
        ],
    )
    body = r.json()
    assert len(body["added"]) == 1 and len(body["refused"]) == 1
    jobs = wait_jobs(client)
    assert jobs[0]["state"] == "done", jobs

    note = brain / "sources/korea-value-up-index-launch.md"
    assert note.is_file()
    text = note.read_text()
    assert "2024년 9월 30일" in text and "67개" in text
    assert not list((brain / "inbox").glob("*.txt"))
    assert (brain / "library/korea-value-up-index-launch.txt").is_file()

    applied = client.get("/api/proposals?status=applied").json()["items"]
    assert applied[0]["approval"] == "auto" and applied[0]["commit"]
    assert any(
        r["id"] == "sources/korea-value-up-index-launch"
        for r in client.get("/api/sources").json()["items"]
    )

    top = client.get("/api/history").json()["items"][0]
    assert top["title"].startswith("자료를 저장했어요")
    undo = client.post(f"/api/history/{top['id']}/undo")
    assert undo.status_code == 200, undo.text
    assert not note.exists() and (brain / "inbox/value-up.txt").exists()
    hist = client.get("/api/history").json()["items"]
    assert hist[0]["undoes"] == top["id"] and hist[1]["undone"] is True


def test_ai_failure_is_reported_on_the_job(client, tmp_path):
    setup_brain(client, tmp_path)
    client.app.state.engine.provider_override = FakeProvider({"title": "broken"})
    client.post("/api/inbox", files=[("files", ("a.txt", TEXT, "text/plain"))])
    job = wait_jobs(client)[0]
    assert job["state"] == "failed" and "형식" in job["message"]


def test_process_inbox_picks_up_files_added_elsewhere(client, tmp_path):
    brain = setup_brain(client, tmp_path)
    (brain / "inbox/manual.txt").write_bytes(TEXT)
    queued = client.post("/api/inbox/process").json()["queued"]
    assert [j["file"] for j in queued] == ["inbox/manual.txt"]
    assert wait_jobs(client)[0]["state"] == "done"


def _pending(engine, path, content):
    p = Proposal(
        agent="test",
        title=f"Edit {path}",
        changes=[FileChange(op="write", path=path, content=content)],
    )
    from brain_core.changes import approval_for

    p.approval = approval_for(p.changes)
    return engine.store.save(p)


def test_cards_approve_reject_and_batch_rules(client, tmp_path):
    brain = setup_brain(client, tmp_path)
    engine = client.app.state.engine
    wiki = _pending(engine, "wiki/concepts/pbr.md", "---\ntitle: PBR\n---\n# PBR\n")
    wiki2 = _pending(engine, "wiki/overviews/margins.md", "# Margins\n\n[[concepts/pbr]]\n")
    memory = _pending(
        engine,
        "memory/records/style.md",
        "---\ntype: preference\nprovenance: user_explicit\nobserved_at: 2026-10-26\n---\n짧은 답을 좋아한다.\n",
    )
    pending = client.get("/api/proposals?status=pending").json()["items"]
    assert {p["approval"] for p in pending} == {"batch", "individual"}
    assert pending[0]["preview"]

    batch = client.post(
        "/api/proposals/approve", json={"ids": [wiki.id, wiki2.id, memory.id]}
    ).json()
    assert {p["id"] for p in batch["items"]} == {
        wiki.id,
        wiki2.id,
    }  # memory is never batch-approved
    assert (brain / "wiki/concepts/pbr.md").exists()

    assert client.post(f"/api/proposals/{memory.id}/reject").json()["status"] == "rejected"
    assert not (brain / "memory/records/style.md").exists()
    again = client.post(f"/api/proposals/{memory.id}/approve")
    assert again.status_code == 409
    assert client.post("/api/proposals/nope/approve").status_code == 404


def test_invalid_change_fails_and_leaves_brain_untouched(client, tmp_path):
    brain = setup_brain(client, tmp_path)
    bad = _pending(client.app.state.engine, "sources/bad.md", "---\ntitle: no type\n---\n")
    result = client.post(f"/api/proposals/{bad.id}/approve").json()
    assert result["status"] == "failed" and "source_type" in result["error"]
    assert not (brain / "sources/bad.md").exists()


def test_undo_refused_after_later_edit(client, tmp_path):
    brain = setup_brain(client, tmp_path)
    p = _pending(client.app.state.engine, "wiki/concepts/a.md", "# A\n")
    commit = client.post(f"/api/proposals/{p.id}/approve").json()["commit"]
    (brain / "wiki/concepts/a.md").write_text("# A edited by the user\n")
    r = client.post(f"/api/history/{commit}/undo")
    assert r.status_code == 409 and "changed again" in r.json()["detail"]


def test_ai_status_without_ollama(client, monkeypatch):
    monkeypatch.setattr(
        "wooju_agents.llm.OllamaProvider.status",
        lambda self: {"running": False, "models": [], "model_ready": False},
    )
    ai = client.get("/api/setup").json()["ai"]
    assert ai["ready"] is False and "Ollama" in ai["message"]


def test_choosing_a_cloud_provider_stores_the_key_in_the_keychain(client, monkeypatch):
    saved = {}
    monkeypatch.setattr(app_settings, "set_api_key", lambda p, k: saved.update({p: k}))
    monkeypatch.setattr(app_settings, "get_api_key", lambda p: saved.get(p))
    status = client.post(
        "/api/setup/ai", json={"provider": "anthropic", "api_key": " sk-ant-x "}
    ).json()
    assert saved == {"anthropic": "sk-ant-x"}
    assert status["provider"] == "anthropic" and status["ready"] is True
    assert "sk-ant" not in app_settings.settings_file().read_text()
