"""One interface over Ollama, OpenAI, and Anthropic.

Every call asks for JSON that matches a JSON Schema, using each provider's own
structured-output feature, so agents never parse free text. Agents depend only
on :class:`Provider`; which model runs is a setting.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from brain_core.messages import UserFacingError

DEFAULT_OLLAMA_HOST = "http://localhost:11434"
# Hardware mapping from docs/DECISIONS.md (Apple Silicon baseline).
OLLAMA_MODEL_SMALL = "qwen3.5:4b"  # 8 GB
OLLAMA_MODEL_LARGE = "qwen3.5:9b"  # 16 GB or more
# Cloud defaults. Users can change them in settings; keep these current.
OPENAI_DEFAULT_MODEL = "gpt-5-mini"
ANTHROPIC_DEFAULT_MODEL = "claude-haiku-5-5"
OLLAMA_CONTEXT = 16384


class LLMError(UserFacingError):
    """The provider could not produce a usable answer.

    ``key`` names the message shown to the user (see brain_core.messages).
    ``retryable`` is True when the AI is simply not available yet (not running,
    model not downloaded, no key): work can wait and continue once it is.
    """

    def __init__(self, detail: str, key: str, retryable: bool = False, **params: Any) -> None:
        super().__init__(detail, key, **params)
        self.retryable = retryable


@dataclass(frozen=True)
class LLMResult:
    data: dict[str, Any]
    raw: str
    seconds: float
    provider: str
    model: str


class Provider(Protocol):
    name: str
    model: str

    def generate_json(self, system: str, user: str, schema: dict[str, Any]) -> LLMResult: ...


def recommended_ollama_model(memory_bytes: int | None = None) -> str:
    """Pick the local model for this Mac's memory (8 GB → 4B, 16 GB+ → 9B)."""
    if memory_bytes is None:
        try:
            memory_bytes = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
        except (ValueError, OSError, AttributeError):
            return OLLAMA_MODEL_SMALL
    return OLLAMA_MODEL_LARGE if memory_bytes >= 15 * 1024**3 else OLLAMA_MODEL_SMALL


def _loads(raw: str, provider: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LLMError(
            f"{provider} returned invalid JSON: {raw[:200]}",
            "llm.unreadable",
        ) from exc
    if not isinstance(value, dict):
        raise LLMError(f"{provider} returned non-object JSON", "llm.unreadable")
    return value


class OllamaProvider:
    name = "ollama"

    def __init__(
        self, model: str, host: str = DEFAULT_OLLAMA_HOST, client: httpx.Client | None = None
    ) -> None:
        self.model = model
        self.host = host.rstrip("/")
        self.client = client or httpx.Client(timeout=600)

    def status(self) -> dict[str, Any]:
        """Is Ollama running, and is the model downloaded?"""
        try:
            resp = self.client.get(f"{self.host}/api/tags", timeout=3)
            resp.raise_for_status()
        except httpx.HTTPError:
            return {"running": False, "models": [], "model_ready": False}
        names = [m.get("name", "") for m in resp.json().get("models", [])]
        return {"running": True, "models": names, "model_ready": self.model in names}

    def installed(self) -> list[dict[str, Any]] | None:
        """Models downloaded in Ollama (name, size in bytes), or None if Ollama is off."""
        try:
            resp = self.client.get(f"{self.host}/api/tags", timeout=3)
            resp.raise_for_status()
        except httpx.HTTPError:
            return None
        return [
            {"name": m.get("name", ""), "size": m.get("size", 0)}
            for m in resp.json().get("models", [])
            if m.get("name")
        ]

    def pull(self) -> None:
        """Download the model through Ollama (may take minutes)."""
        try:
            resp = self.client.post(
                f"{self.host}/api/pull", json={"model": self.model, "stream": False}, timeout=None
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMError(str(exc), "llm.pull_failed") from exc

    def generate_json(self, system: str, user: str, schema: dict[str, Any]) -> LLMResult:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "format": schema,
            "stream": False,
            "think": False,
            # Ollama's default context (2–4K tokens) silently cuts long sources
            # and Ask's passages; 16K fits both on an 8 GB Mac with the 4B model.
            "options": {"temperature": 0, "num_ctx": OLLAMA_CONTEXT},
        }
        start = time.monotonic()
        try:
            resp = self.client.post(f"{self.host}/api/chat", json=payload)
            if resp.status_code == 400 and "think" in resp.text:
                payload.pop("think")
                resp = self.client.post(f"{self.host}/api/chat", json=payload)
            resp.raise_for_status()
        except httpx.ConnectError as exc:
            raise LLMError(str(exc), "llm.ollama_off", retryable=True) from exc
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise LLMError(
                    str(exc), "llm.model_missing", retryable=True, model=self.model
                ) from exc
            raise LLMError(str(exc), "llm.no_response") from exc
        except httpx.HTTPError as exc:
            raise LLMError(str(exc), "llm.no_response") from exc
        raw = (resp.json().get("message") or {}).get("content", "")
        return LLMResult(
            _loads(raw, self.name), raw, time.monotonic() - start, self.name, self.model
        )


class OpenAIProvider:
    name = "openai"

    def __init__(
        self,
        api_key: str,
        model: str = OPENAI_DEFAULT_MODEL,
        client: httpx.Client | None = None,
        base_url: str = "https://api.openai.com/v1",
    ) -> None:
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.client = client or httpx.Client(timeout=120)

    def generate_json(self, system: str, user: str, schema: dict[str, Any]) -> LLMResult:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "output", "schema": schema},
            },
        }
        start = time.monotonic()
        try:
            resp = self.client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 401:
                raise LLMError(str(exc), "llm.openai_key") from exc
            raise LLMError(str(exc), "llm.openai_down") from exc
        except httpx.HTTPError as exc:
            raise LLMError(str(exc), "llm.offline") from exc
        raw = resp.json()["choices"][0]["message"].get("content") or ""
        return LLMResult(
            _loads(raw, self.name), raw, time.monotonic() - start, self.name, self.model
        )


class AnthropicProvider:
    name = "anthropic"

    def __init__(
        self,
        api_key: str,
        model: str = ANTHROPIC_DEFAULT_MODEL,
        client: httpx.Client | None = None,
        base_url: str = "https://api.anthropic.com/v1",
    ) -> None:
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.client = client or httpx.Client(timeout=120)

    def generate_json(self, system: str, user: str, schema: dict[str, Any]) -> LLMResult:
        # A forced tool call is Anthropic's way to get schema-shaped JSON.
        payload = {
            "model": self.model,
            "max_tokens": 4096,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "tools": [
                {"name": "output", "description": "Return the result.", "input_schema": schema}
            ],
            "tool_choice": {"type": "tool", "name": "output"},
        }
        start = time.monotonic()
        try:
            resp = self.client.post(
                f"{self.base_url}/messages",
                json=payload,
                headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01"},
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 401:
                raise LLMError(str(exc), "llm.claude_key") from exc
            raise LLMError(str(exc), "llm.claude_down") from exc
        except httpx.HTTPError as exc:
            raise LLMError(str(exc), "llm.offline") from exc
        for block in resp.json().get("content", []):
            if block.get("type") == "tool_use":
                data = block.get("input") or {}
                return LLMResult(
                    data,
                    json.dumps(data, ensure_ascii=False),
                    time.monotonic() - start,
                    self.name,
                    self.model,
                )
        raise LLMError("Anthropic returned no tool_use block", "llm.unreadable")
