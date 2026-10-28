"""Capture through iCloud Drive/Wooju Inbox."""

from __future__ import annotations

import time

import anyio
import pytest
from fake_ai import cited
from fastapi.testclient import TestClient

from app import icloud
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
LONG = ("Korea Value-up Index starts next week. 100 stocks: 67 on Kospi. " * 30).encode()


class Fake:
    name, model = "fake", "fake"

    def generate_json(self, system, user, schema):
        return LLMResult(cited(DRAFT, user, schema), "", 0.0, self.name, self.model)


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.delenv("WOOJU_BRAIN_PATH", raising=False)
    monkeypatch.setenv("WOOJU_ICLOUD_DIR", str(tmp_path / "iCloud"))
    (tmp_path / "iCloud").mkdir()
    with TestClient(app) as c:
        c.app.state.engine.provider_override = Fake()
        assert c.post("/api/setup/brain", json={"path": str(tmp_path / "B")}).status_code == 200
        yield c, tmp_path / "B"


def poll(c):
    return anyio.run(c.app.state.engine.poll_icloud)


def wait_jobs(c, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        items = c.get("/api/jobs").json()["items"]
        if items and all(j["state"] in ("done", "failed") for j in items):
            return items
        time.sleep(0.05)
    raise AssertionError(items)


def test_turn_on_creates_the_folder(client):
    c, _ = client
    status = c.post("/api/capture/icloud", json={"enabled": True}).json()
    assert status["icloud"]["enabled"] and icloud.capture_folder().is_dir()


def test_files_are_taken_only_when_finished(client):
    c, brain = client
    c.post("/api/capture/icloud", json={"enabled": True})
    folder = icloud.capture_folder()
    (folder / "report.txt").write_bytes(LONG)
    (folder / ".Report2.pdf.icloud").write_bytes(b"placeholder")

    assert poll(c) == 0  # first sight: might still be syncing
    assert poll(c) == 1
    assert not (folder / "report.txt").exists()
    assert (folder / ".Report2.pdf.icloud").exists()
    assert wait_jobs(c)[0]["state"] == "done"
    assert (brain / "sources/korea-value-up-index-launch.md").is_file()
    assert c.get("/api/capture/status").json()["recent"][0]["kind"] == "file"


def test_short_text_is_a_memo(client):
    c, brain = client
    c.post("/api/capture/icloud", json={"enabled": True})
    (icloud.capture_folder() / "memo.txt").write_text("HBM 비중 다시 보기", encoding="utf-8")
    poll(c)
    poll(c)
    memos = list((brain / "inbox/memos").glob("*.md"))
    assert len(memos) == 1 and "HBM" in memos[0].read_text(encoding="utf-8")


def test_unsupported_files_are_set_aside(client):
    c, _ = client
    c.post("/api/capture/icloud", json={"enabled": True})
    folder = icloud.capture_folder()
    (folder / "photo.heic").write_bytes(b"x")
    poll(c)
    poll(c)
    assert (folder / "Not supported" / "photo.heic").exists()
    assert c.get("/api/capture/status").json()["recent"][0]["kind"] == "refused"


def test_off_by_default(client):
    c, _ = client
    folder = icloud.ensure_folder()
    (folder / "report.txt").write_bytes(LONG)
    poll(c)
    poll(c)
    assert (folder / "report.txt").exists()


def test_icloud_drive_missing(client, monkeypatch, tmp_path):
    c, _ = client
    monkeypatch.setenv("WOOJU_ICLOUD_DIR", str(tmp_path / "nope"))
    r = c.post("/api/capture/icloud", json={"enabled": True})
    assert r.status_code == 400
