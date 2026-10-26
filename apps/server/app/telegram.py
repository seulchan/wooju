"""Capture from Telegram through the user's own bot.

Setup is three steps in Settings: make a bot with @BotFather, paste its token,
press Start in the chat Wooju opens. The token lives in the macOS keychain.
The first chat that starts the bot with this Mac's pairing code becomes the
only chat Wooju listens to; anyone else who finds the bot gets a refusal and
nothing is saved.

While Wooju is open it long-polls Telegram (no server, no open ports). Text is
a link or a memo, documents are files; the bot replies with what happened.
Telegram keeps messages for 24 hours, so things sent while the Mac was off
arrive when Wooju next opens. The processed position is saved, so nothing is
handled twice after a restart.

The token is part of every Bot API URL, so request logging is kept quiet.
"""

from __future__ import annotations

import json
import logging
import secrets
from pathlib import Path
from typing import Any

import httpx

from brain_core.changes import data_dir

# httpx logs full URLs at INFO, and Bot API URLs contain the token.
logging.getLogger("httpx").setLevel(logging.WARNING)

API = "https://api.telegram.org"
KEY_NAME = "telegram"
MAX_FILE = 20 * 1024 * 1024  # the Bot API's download limit


class TelegramError(Exception):
    pass


class Bot:
    def __init__(self, token: str, client: httpx.Client | None = None) -> None:
        self._token = token
        self.client = client or httpx.Client(timeout=40)

    def __repr__(self) -> str:  # never show the token
        return "Bot(<token hidden>)"

    def call(self, method: str, **params: Any) -> Any:
        try:
            resp = self.client.post(f"{API}/bot{self._token}/{method}", json=params)
            data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise TelegramError(f"{method} failed: {type(exc).__name__}") from exc
        if not data.get("ok"):
            raise TelegramError(f"{method}: {data.get('description', 'error')}")
        return data["result"]

    def me(self) -> dict[str, Any]:
        return self.call("getMe")

    def updates(self, offset: int | None, timeout: int = 25) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"timeout": timeout, "allowed_updates": ["message"]}
        if offset is not None:
            params["offset"] = offset
        return self.call("getUpdates", **params)

    def send(self, chat_id: int, text: str) -> None:
        try:
            self.call("sendMessage", chat_id=chat_id, text=text)
        except TelegramError:
            pass  # a lost reply must never lose the captured item

    def download(self, file_id: str) -> bytes:
        info = self.call("getFile", file_id=file_id)
        if info.get("file_size", 0) > MAX_FILE:
            raise TelegramError("too big")
        try:
            resp = self.client.get(f"{API}/file/bot{self._token}/{info['file_path']}")
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise TelegramError(f"download failed: {type(exc).__name__}") from exc
        return resp.content


# ----------------------------------------------------------------- state


def _state_file() -> Path:
    return data_dir() / "telegram.json"


def load_state() -> dict[str, Any]:
    try:
        return json.loads(_state_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(state: dict[str, Any]) -> None:
    path = _state_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state), encoding="utf-8")


def new_pairing_code() -> str:
    return secrets.token_urlsafe(8).replace("-", "a").replace("_", "b")


def pairing_code_in(text: str) -> str | None:
    """The code from '/start <code>' (what Telegram sends from a t.me/bot?start= link)."""
    parts = text.strip().split()
    if len(parts) == 2 and parts[0].split("@")[0] == "/start":
        return parts[1]
    return None
