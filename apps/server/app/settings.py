"""App settings and API keys, stored outside the Brain.

Settings live in ``<data dir>/settings.json`` (``~/.wooju`` unless
``WOOJU_DATA_DIR`` is set). API keys never touch a file: they go to the
operating system's keychain through ``keyring``.
"""

from __future__ import annotations

import json
import logging
from typing import Literal

from pydantic import BaseModel, Field

from brain_core.changes import data_dir
from wooju_agents.llm import DEFAULT_OLLAMA_HOST

logger = logging.getLogger("wooju")

KEYRING_SERVICE = "Wooju"
ProviderName = Literal["ollama", "openai", "anthropic"]


class AiSettings(BaseModel):
    provider: ProviderName = "ollama"
    model: str | None = None  # None → the recommended model for this Mac / provider
    ollama_host: str = DEFAULT_OLLAMA_HOST


class CaptureSettings(BaseModel):
    icloud: bool = False  # pick up files from iCloud Drive/Wooju Inbox
    telegram: bool = False  # the bot token itself is in the keychain
    telegram_chat_id: int | None = None  # the one chat allowed to send


LanguageSetting = Literal["auto", "ko", "en"]


class AppSettings(BaseModel):
    brain_path: str | None = None
    language: LanguageSetting = "auto"  # "auto" follows the Mac
    ai: AiSettings = Field(default_factory=AiSettings)
    capture: CaptureSettings = Field(default_factory=CaptureSettings)


class KeyStoreError(Exception):
    pass


def settings_file():
    return data_dir() / "settings.json"


def load() -> AppSettings:
    path = settings_file()
    try:
        return AppSettings.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except FileNotFoundError:
        return AppSettings()
    except (OSError, ValueError) as exc:
        logger.warning("Ignoring unreadable settings %s: %s", path, exc)
        return AppSettings()


def save(settings: AppSettings) -> None:
    path = settings_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(settings.model_dump_json(indent=2), encoding="utf-8")
    tmp.replace(path)


def get_api_key(provider: str) -> str | None:
    try:
        import keyring

        return keyring.get_password(KEYRING_SERVICE, provider)
    except Exception:  # noqa: BLE001 — no keychain means no stored key
        return None


def set_api_key(provider: str, key: str) -> None:
    try:
        import keyring

        keyring.set_password(KEYRING_SERVICE, provider, key)
    except Exception as exc:  # noqa: BLE001
        raise KeyStoreError(str(exc)) from exc


def delete_api_key(provider: str) -> None:
    try:
        import keyring

        keyring.delete_password(KEYRING_SERVICE, provider)
    except Exception:  # noqa: BLE001 — nothing stored is fine
        pass
