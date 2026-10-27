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
    assert client.get("/api/history").json()["items"][0]["title"] == "Brain 시작"

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
    assert r.status_code == 409 and "다시 바뀌어서" in r.json()["detail"]


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


class DownProvider:
    name, model = "ollama", "qwen3.5:4b"

    def generate_json(self, system, user, schema):
        from wooju_agents.llm import LLMError

        raise LLMError("refused", "Ollama가 실행 중이 아니에요.", retryable=True)


def test_files_wait_for_the_ai_and_continue_when_it_is_ready(client, tmp_path, monkeypatch):
    brain = setup_brain(client, tmp_path)
    engine = client.app.state.engine
    engine.provider_override = DownProvider()
    client.post("/api/inbox", files=[("files", ("a.txt", TEXT, "text/plain"))])
    deadline = time.time() + 5
    while (
        time.time() < deadline and client.get("/api/jobs").json()["items"][0]["state"] != "waiting"
    ):
        time.sleep(0.05)
    job = client.get("/api/jobs").json()["items"][0]
    assert job["state"] == "waiting" and "자동으로" in job["message"]
    assert (brain / "inbox/a.txt").exists()

    engine.provider_override = FakeProvider()
    monkeypatch.setattr(engine, "ai_ready", lambda: True)
    client.portal.call(engine.retry_waiting)
    assert wait_jobs(client)[0]["state"] == "done"
    assert (brain / "sources/korea-value-up-index-launch.md").exists()


def test_open_url_only_opens_web_pages(client, monkeypatch):
    """Web links (setup pages, links in notes) open in the browser; nothing else does."""
    opened = []
    monkeypatch.setattr("webbrowser.open", lambda url: opened.append(url))
    monkeypatch.setattr("subprocess.run", lambda args, **kw: opened.append(args[-1]))
    assert client.post("/api/open", json={"url": "https://ollama.com/download"}).status_code == 200
    assert client.post("/api/open", json={"url": "file:///etc/passwd"}).status_code == 403
    assert client.post("/api/open", json={"url": "/Applications/Calculator.app"}).status_code == 403
    assert opened == ["https://ollama.com/download"]


def test_launcher_uses_bundle_paths(monkeypatch, tmp_path):
    import sys

    from app import launcher

    calls = {}
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    # setenv first so monkeypatch restores both variables after the test;
    # the launcher writes os.environ directly.
    for name in ("WOOJU_WEB_DIST", "WOOJU_TEMPLATE_DIR"):
        monkeypatch.setenv(name, "unset")
        monkeypatch.delenv(name)
    monkeypatch.setattr("uvicorn.run", lambda app, **kw: calls.update(kw))
    launcher.main(["--port", "9123"])
    import os

    assert calls == {"host": "127.0.0.1", "port": 9123, "log_level": "info"}
    assert os.environ["WOOJU_WEB_DIST"] == str(tmp_path / "web")
    assert os.environ["WOOJU_TEMPLATE_DIR"] == str(tmp_path / "template")


def test_english_mac_gets_english_messages(client, tmp_path, monkeypatch):
    monkeypatch.setenv("WOOJU_LANGUAGE", "en")
    busy = tmp_path / "busy"
    busy.mkdir()
    (busy / "x.txt").write_text("x")
    r = client.post("/api/setup/brain", json={"path": str(busy)})
    assert (
        r.json()["detail"] == "This folder already has other files. Choose an empty or new folder."
    )
    brain = setup_brain(client, tmp_path)
    titles = [i["title"] for i in client.get("/api/history").json()["items"]]
    assert titles == ["Start this Brain"]
    r = client.post("/api/inbox", files=[("files", ("a.heic", b"x", "image/heic"))])
    assert r.json()["refused"][0]["message"].startswith("'a.heic' can't be read yet")
    assert brain.exists()


def test_history_titles_in_korean():
    from app.api.actions import display_title

    assert display_title("Received report.pdf", "ko") == "받은 파일: report.pdf"
    assert display_title("Received 3 file(s)", "ko") == "파일 3개 받음"
    assert display_title("Undo: Received a.txt", "ko") == "되돌림: 받은 파일: a.txt"
    assert display_title("자료를 저장했어요: X", "ko") == "자료를 저장했어요: X"
    assert display_title("Received a.txt", "en") == "Received a.txt"


def test_model_list_and_choice(client, monkeypatch):
    monkeypatch.setattr(
        "wooju_agents.llm.OllamaProvider.installed",
        lambda self: [
            {"name": "qwen3.5:9b", "size": 6600000000},
            {"name": "llama3.2:3b", "size": 2000000000},
        ],
    )
    monkeypatch.setattr(
        "wooju_agents.llm.OllamaProvider.status",
        lambda self: {
            "running": True,
            "models": ["qwen3.5:9b", "llama3.2:3b"],
            "model_ready": self.model in ("qwen3.5:9b", "llama3.2:3b"),
        },
    )
    monkeypatch.setattr("app.api.actions.recommended_ollama_model", lambda: "qwen3.5:9b")
    models = client.get("/api/setup/ai/models").json()
    assert models["running"] is True and models["current"] == "qwen3.5:9b"
    assert [m["name"] for m in models["installed"]] == ["llama3.2:3b", "qwen3.5:9b"]
    assert [m["recommended"] for m in models["installed"]] == [False, True]
    assert {s["name"]: s["installed"] for s in models["suggested"]} == {
        "qwen3.5:4b": False,
        "qwen3.5:9b": True,
    }

    status = client.post(
        "/api/setup/ai", json={"provider": "ollama", "model": "llama3.2:3b"}
    ).json()
    assert status["model"] == "llama3.2:3b" and status["ready"] is True
    assert app_settings.load().ai.model == "llama3.2:3b"
    assert client.get("/api/setup/ai/models").json()["current"] == "llama3.2:3b"

    bad = client.post("/api/setup/ai", json={"provider": "ollama", "model": "x; rm -rf /"})
    assert bad.status_code == 400


def test_models_when_ollama_is_off(client, monkeypatch):
    monkeypatch.setattr("wooju_agents.llm.OllamaProvider.installed", lambda self: None)
    models = client.get("/api/setup/ai/models").json()
    assert models["running"] is False and models["installed"] == []


def test_pull_a_chosen_model(client, monkeypatch):
    pulled = []
    monkeypatch.setattr(
        "wooju_agents.llm.OllamaProvider.pull", lambda self: pulled.append(self.model)
    )
    client.post("/api/setup/ai/pull", json={"model": "llama3.2:3b"})
    deadline = time.time() + 5
    while time.time() < deadline and client.app.state.engine.pull_state["state"] == "pulling":
        time.sleep(0.05)
    assert pulled == ["llama3.2:3b"]
    assert client.app.state.engine.pull_state["state"] == "done"


def test_pick_folder(client, monkeypatch):
    import subprocess as sp

    monkeypatch.setattr("app.api.actions.sys.platform", "darwin")
    monkeypatch.setattr(
        "app.api.actions.subprocess.run",
        lambda args, **kw: sp.CompletedProcess(
            args, 0, stdout="/Users/me/Documents/Wooju/\n", stderr=""
        ),
    )
    assert client.post("/api/setup/pick-folder").json() == {"path": "/Users/me/Documents/Wooju"}
    monkeypatch.setattr(
        "app.api.actions.subprocess.run",
        lambda args, **kw: sp.CompletedProcess(args, 1, stdout="", stderr="User canceled."),
    )
    assert client.post("/api/setup/pick-folder").json() == {"path": None}


# ------------------------------------------------------------------ capture

PAGE = (
    "<html><head><title>Value-up</title></head><body><p>"
    + "Korea Value-up Index to begin publication next week. 100 stocks. " * 5
    + "</p></body></html>"
).encode()


def _fake_fetch(monkeypatch):
    from wooju_agents import capture

    def fake(url, client=None):
        return PAGE, ".html", "https://news.example.com/value-up"

    monkeypatch.setattr(capture, "fetch", fake)


def test_paste_a_link_and_it_becomes_a_source(client, tmp_path, monkeypatch):
    brain = setup_brain(client, tmp_path)
    _fake_fetch(monkeypatch)
    r = client.post("/api/capture", json={"text": "읽어볼 것 https://example.com/short"})
    assert r.status_code == 200, r.text
    assert r.json()["kind"] == "link"
    jobs = wait_jobs(client)
    assert jobs[0]["state"] == "done", jobs
    note = (brain / "sources/korea-value-up-index-launch.md").read_text(encoding="utf-8")
    assert "canonical_ref: https://news.example.com/value-up" in note


def test_paste_a_memo_and_it_is_kept_as_written(client, tmp_path):
    brain = setup_brain(client, tmp_path)
    r = client.post("/api/capture", json={"text": "삼성전자 HBM 비중이 30%를 넘으면 다시 볼 것"})
    assert r.status_code == 200 and r.json()["kind"] == "memo"
    rel = r.json()["file"]
    assert rel.startswith("inbox/memos/")
    assert "HBM 비중" in (brain / rel).read_text(encoding="utf-8")
    assert client.get("/api/jobs").json()["items"] == []  # not sent to the AI
    hits = client.get("/api/search", params={"q": "HBM"}).json()["hits"]
    assert hits and hits[0]["category"] == "memory"


def test_drop_a_link_file(client, tmp_path, monkeypatch):
    import plistlib

    brain = setup_brain(client, tmp_path)
    _fake_fetch(monkeypatch)
    data = plistlib.dumps({"URL": "https://example.com/x"})
    r = client.post(
        "/api/inbox", files=[("files", ("article.webloc", data, "application/octet-stream"))]
    )
    assert len(r.json()["added"]) == 1
    jobs = wait_jobs(client)
    assert jobs[0]["state"] == "done", jobs
    assert not list((brain / "inbox").glob("*.webloc"))
    assert (brain / "sources/korea-value-up-index-launch.md").is_file()


def test_bad_link(client, tmp_path):
    setup_brain(client, tmp_path)
    r = client.post("/api/capture", json={"text": "http://127.0.0.1:8000/api/setup"})
    assert r.status_code == 400 and "링크" in r.json()["detail"]


def test_app_follows_the_mac_and_notes_follow_the_brain(client, tmp_path, monkeypatch):
    """A Korean Brain on an English Mac: English app, Korean notes."""
    monkeypatch.setenv("WOOJU_LANGUAGE", "en")  # stands in for the Mac's language
    brain = setup_brain(client, tmp_path)
    cfg = brain / "wooju-brain.yaml"
    cfg.write_text(cfg.read_text().replace("language: auto", "language: ko"), encoding="utf-8")

    assert client.get("/api/setup").json()["language"] == "en"
    client.post("/api/inbox", files=[("files", ("value-up.txt", TEXT, "text/plain"))])
    assert wait_jobs(client)[0]["state"] == "done"
    note = (brain / "sources/korea-value-up-index-launch.md").read_text(encoding="utf-8")
    assert "## 한 줄 요약" in note
    applied = client.get("/api/proposals?status=applied").json()["items"]
    assert applied[0]["title"].startswith("Saved source:")


def test_open_links_and_files_from_notes(client, tmp_path, monkeypatch):
    import subprocess

    opened = []

    def fake_run(args, **kwargs):
        opened.append(args)
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr("sys.platform", "darwin")
    brain = setup_brain(client, tmp_path)
    (brain / "library").mkdir(exist_ok=True)
    (brain / "library" / "report.pdf").write_bytes(b"%PDF")

    assert client.post("/api/open-file", json={"path": "library/report.pdf"}).status_code == 200
    assert [a for a in opened if a[0] == "open"][-1][-1].endswith("library/report.pdf")
    assert client.post("/api/open-file", json={"path": "../../etc/passwd"}).status_code == 404
    assert client.post("/api/open-file", json={"path": "library/nope.pdf"}).status_code == 404

    assert (
        client.post("/api/open", json={"url": "https://en.wikipedia.org/wiki/KOSPI"}).status_code
        == 200
    )
    for bad in ("file:///etc/passwd", "javascript:alert(1)", "-a Calculator", "https://x.com/a b"):
        assert client.post("/api/open", json={"url": bad}).status_code == 403, bad
