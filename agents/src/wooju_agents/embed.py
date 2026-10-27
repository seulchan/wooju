"""Meaning search: embeddings from a small local model in Ollama.

Embeddings always run on this Mac, even when the user answers questions with
Claude or OpenAI, so the whole Brain is never sent anywhere just to be
indexed. If Ollama or the model is missing, search falls back to keywords.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import httpx

from brain_core.vectors import normalize

from .llm import DEFAULT_OLLAMA_HOST, LLMError

EMBED_MODEL = "qwen3-embedding:0.6b"
# Qwen3-Embedding is instruction-aware on the query side only.
_QUERY = "Instruct: Given a question, retrieve notes and passages that answer it\nQuery: {q}"
BATCH = 16
EMBED_CONTEXT = 2048


class Embedder:
    def __init__(
        self,
        model: str = EMBED_MODEL,
        host: str = DEFAULT_OLLAMA_HOST,
        client: httpx.Client | None = None,
    ) -> None:
        self.model = model
        self.host = host.rstrip("/")
        self.client = client or httpx.Client(timeout=300)

    def ready(self) -> bool:
        """Ollama is running and the embedding model is downloaded."""
        try:
            resp = self.client.get(f"{self.host}/api/tags", timeout=3)
            resp.raise_for_status()
        except httpx.HTTPError:
            return False
        names = {m.get("name", "") for m in resp.json().get("models", [])}
        return self.model in names or f"{self.model}:latest" in names

    def _embed(self, texts: Sequence[str]) -> list[list[float]]:
        try:
            resp = self.client.post(
                f"{self.host}/api/embed",
                json={
                    "model": self.model,
                    "input": list(texts),
                    "truncate": True,
                    # Passages are short. Ollama's default context for this model
                    # reserves ~3.5 GB, which pushed the answer model out of
                    # memory on a 16 GB Mac; 2K tokens needs a few hundred MB.
                    "options": {"num_ctx": EMBED_CONTEXT},
                    "keep_alive": "2m",
                },
            )
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
        data: Any = resp.json().get("embeddings") or []
        if len(data) != len(texts):
            raise LLMError("embedding count mismatch", "llm.unreadable")
        return data

    def documents(self, texts: Sequence[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for start in range(0, len(texts), BATCH):
            out.extend(self._embed(texts[start : start + BATCH]))
        return out

    def query(self, question: str) -> Sequence[float]:
        return normalize(self._embed([_QUERY.format(q=question)])[0])
