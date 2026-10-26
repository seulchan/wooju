"""Telegram capture with a fake Bot API: pairing, privacy, links, memos, files."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from app import settings as app_settings
from app import telegram
from app.main import app
from wooju_agents.llm import LLMResult

TOKEN = "123456789:" + "A" * 35
DRAFT = {
    "title": "Korea Value-up Index launch",
    "source_type": "article",
    "authors": [],
    "published": "2024-09-24",
    "one_line_summary": "100 stocks.",
    "key_points": ["67 on Kospi"],
    "limitations": [],
}
LONG = ("Korea Value-up Index to begin publication next week. 100 stocks. " * 30).encode()


class Fake:
    name, model = "fake", "fake"

    def generate_json(self, system, user, schema):
        return LLMResult(DRAFT, "", 0.0, self.name, self.model)


class FakeBot:
    """Stands in for the Bot API. Tests push updates; replies are recorded."""

    instances: list[FakeBot] = []
    inbox: list[dict] = []
    sent: list[tuple[int, str]] = []
    files: dict[str, bytes] = {}

    def __init__(self, token):
        if token != TOKEN:
            raise AssertionError("wrong token")
        FakeBot.instances.append(self)

    def me(self):
        return {"username": "my_wooju_bot"}

    def updates(self, offset, timeout=25):
        # Like Telegram: updates stay until a later call confirms them with offset.
        time.sleep(0.02)
        return [u for u in FakeBot.inbox if offset is None or u["update_id"] >= offset]

    def send(self, chat_id, text):
        FakeBot.sent.append((chat_id, text))

    def download(self, file_id):
        return FakeBot.files[file_id]


_update_id = 0


def push(chat_id, **message):
    global _update_id
    _update_id += 1
    FakeBot.inbox.append({"update_id": _update_id, "message": {"chat": {"id": chat_id}, **message}})


def wait_for(cond, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if cond():
            return
        time.sleep(0.05)
    raise AssertionError(f"timed out; sent={FakeBot.sent}")


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.delenv("WOOJU_BRAIN_PATH", raising=False)
    monkeypatch.setenv("WOOJU_LANGUAGE", "en")
    keys = {}
    monkeypatch.setattr(app_settings, "set_api_key", lambda name, key: keys.__setitem__(name, key))
    monkeypatch.setattr(app_settings, "get_api_key", lambda name: keys.get(name))
    monkeypatch.setattr(app_settings, "delete_api_key", lambda name: keys.pop(name, None))
    FakeBot.inbox, FakeBot.sent, FakeBot.files, FakeBot.instances = [], [], {}, []
    with TestClient(app) as c:
        engine = c.app.state.engine
        engine.provider_override = Fake()
        engine.telegram_factory = FakeBot
        assert c.post("/api/setup/brain", json={"path": str(tmp_path / "B")}).status_code == 200
        yield c, tmp_path / "B", keys


def connect(c):
    r = c.post("/api/capture/telegram", json={"token": TOKEN})
    assert r.status_code == 200, r.text
    return r.json()["telegram"]


def pair(c, chat_id=42):
    status = connect(c)
    code = status["pair_link"].split("start=")[1]
    push(chat_id, text=f"/start {code}")
    wait_for(lambda: app_settings.load().capture.telegram_chat_id == chat_id)


def test_connect_keeps_token_in_keychain_and_offers_a_pairing_link(client):
    c, _, keys = client
    status = connect(c)
    assert keys["telegram"] == TOKEN
    assert status["bot"] == "my_wooju_bot" and not status["paired"]
    assert status["pair_link"].startswith("https://t.me/my_wooju_bot?start=")
    assert TOKEN not in str(c.get("/api/capture/status").json())


def test_bad_token_is_refused(client):
    c, _, keys = client
    r = c.post("/api/capture/telegram", json={"token": "not-a-token"})
    assert r.status_code == 400 and "telegram" not in keys


def test_only_the_paired_chat_is_heard(client):
    c, brain, _ = client
    connect(c)
    push(7, text="/start wrong-code")
    wait_for(lambda: any(chat == 7 for chat, _ in FakeBot.sent))
    assert app_settings.load().capture.telegram_chat_id is None

    pair(c, chat_id=42)
    assert c.get("/api/capture/status").json()["telegram"]["paired"]
    push(99, text="삼성전자 메모")
    wait_for(lambda: (99, "This bot is private.") in FakeBot.sent)
    assert not (brain / "inbox/memos").exists()


def test_memo_link_and_file(client, monkeypatch):
    c, brain, _ = client
    pair(c)

    push(42, text="HBM 비중 다시 보기")
    wait_for(lambda: (42, "Memo saved.") in FakeBot.sent)
    assert len(list((brain / "inbox/memos").glob("*.md"))) == 1

    FakeBot.files["f1"] = LONG
    push(42, document={"file_id": "f1", "file_name": "report.txt"})
    wait_for(lambda: any(t.startswith("✓") for _, t in FakeBot.sent))
    assert (brain / "sources/korea-value-up-index-launch.md").is_file()

    push(42, photo=[{"file_id": "p"}])
    wait_for(lambda: any("Photos can't be read" in t for _, t in FakeBot.sent))


def test_turn_off_forgets_the_token(client):
    c, _, keys = client
    pair(c)
    status = c.post("/api/capture/telegram/off").json()["telegram"]
    assert not status["enabled"] and "telegram" not in keys
    assert app_settings.load().capture.telegram_chat_id is None


def test_offset_survives_restart(client):
    c, _, _ = client
    pair(c)
    assert telegram.load_state()["offset"] == _update_id + 1


def test_only_telegram_bot_links_can_be_opened(client, monkeypatch):
    import subprocess

    c, _, _ = client
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: None)
    import webbrowser

    monkeypatch.setattr(webbrowser, "open", lambda url: None)
    assert (
        c.post("/api/open", json={"url": "https://t.me/my_wooju_bot?start=abcdef12"}).status_code
        == 200
    )
    assert c.post("/api/open", json={"url": "https://t.me/BotFather"}).status_code == 200
    assert c.post("/api/open", json={"url": "https://t.me.evil.com/x"}).status_code == 403
    assert c.post("/api/open", json={"url": "https://t.me/a?start=x;rm"}).status_code == 403
