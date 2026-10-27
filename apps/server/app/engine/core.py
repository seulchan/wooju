"""The running app: which Brain is open, its index, the ingest queue, and writes.

All writes to a Brain go through :class:`Engine` and are serialized by one lock,
so the ingest worker and the user's approvals never interleave. Every write ends
with a rescan, so the UI reflects the change even when file watching is off.
"""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path
from typing import Any

import yaml

from brain_core import history
from brain_core.changes import (
    FileChange,
    Proposal,
    ProposalStore,
    apply_proposal,
    reject_proposal,
)
from brain_core.index import BrainIndex
from brain_core.retrieve import RetrieverCache
from wooju_agents.embed import Embedder
from wooju_agents.llm import (
    AnthropicProvider,
    LLMError,
    OllamaProvider,
    OpenAIProvider,
    Provider,
    recommended_ollama_model,
)
from wooju_agents.text import detect_language, resolve_language

from .. import icloud, telegram
from .. import settings as app_settings
from ..config import resolve_brain_path, watch_enabled
from ..watcher import watch_and_refresh
from .base import (
    Job,
    SetupError,
    create_or_open_brain,
)
from .capture import CaptureMixin
from .editing import EditingMixin
from .ingest import IngestMixin
from .search import SearchMixin
from .telegram_bot import TelegramBotMixin
from .thinking import ThinkingMixin


class Engine(CaptureMixin, IngestMixin, TelegramBotMixin, SearchMixin, EditingMixin, ThinkingMixin):
    def __init__(self) -> None:
        self.index = BrainIndex()
        self.brain: Path | None = None
        self.store = ProposalStore()
        self.jobs: dict[str, Job] = {}
        self.queue: asyncio.Queue[Job] = asyncio.Queue()
        self.lock = asyncio.Lock()
        # One AI task at a time (organizing a file, indexing a batch, answering,
        # challenging). Two models at once can exhaust a 16 GB Mac's memory,
        # and one at a time is also faster than two competing for the GPU.
        # Saving a memo or a link file needs no AI and never waits here.
        self.ai_lane = asyncio.Lock()
        self._worker: asyncio.Task[None] | None = None
        self._watcher: asyncio.Task[None] | None = None
        self._retry: asyncio.Task[None] | None = None
        self.retrievers = RetrieverCache()
        self.embedder_override: Embedder | None = None  # tests
        # Meaning-search indexing progress, shown in Settings.
        self.search_state: dict[str, Any] = {"state": "off", "done": 0, "total": 0}
        self._embedding: asyncio.Task[None] | None = None
        self.icloud_watch = icloud.Watcher()
        self.telegram_factory: Any = telegram.Bot  # tests replace this
        self.telegram_task: asyncio.Task[None] | None = None
        self.telegram_bot_name: str | None = None
        self.telegram_pair_code: str = telegram.new_pairing_code()
        self.capture_log: list[dict[str, Any]] = []  # recent captures, newest first
        self.provider_override: Provider | None = None  # tests
        self.pull_state: dict[str, str | None] = {"model": None, "state": None, "message": None}

    # ------------------------------------------------------------ lifecycle

    async def start(self) -> None:
        path = resolve_brain_path()
        if path is not None and path.is_dir():
            await self.open(path)
        self._worker = asyncio.create_task(self._work(), name="wooju-ingest")
        await self.start_telegram()
        if self.brain is not None:
            # Files left in the inbox (added while closed, or not finished last
            # time) are picked up again; duplicates of saved links are skipped.
            with contextlib.suppress(Exception):
                await self.enqueue_inbox()
        self._retry = asyncio.create_task(self._retry_loop(), name="wooju-retry")

    async def stop(self) -> None:
        for task in (self._worker, self._watcher, self._retry, self.telegram_task):
            if task is not None:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    async def open(self, path: Path) -> None:
        self.brain = path
        await asyncio.to_thread(self.index.scan, path)
        if self._watcher is not None:
            self._watcher.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._watcher
            self._watcher = None
        if watch_enabled():
            self._watcher = asyncio.create_task(watch_and_refresh(self.index, path))
        asyncio.create_task(self.refresh_vectors(), name="wooju-embed-start")

    async def choose_brain(self, path: Path) -> bool:
        created = await asyncio.to_thread(create_or_open_brain, path)
        current = app_settings.load()
        current.brain_path = str(path.expanduser().resolve())
        app_settings.save(current)
        await self.open(path.expanduser().resolve())
        return created

    # ------------------------------------------------------------ settings

    def language(self) -> str:
        """The app's own language (screens, messages, bot replies).

        Chosen in Settings; "auto" follows the Mac.
        """
        return resolve_language(app_settings.load().language)

    def fixed_content_language(self) -> str | None:
        """A language the Brain pins notes to (``content.language``), if any.

        Not shown in the app: by default ("auto") each note keeps the language
        of what it is about.
        """
        if self.brain is not None:
            try:
                data = yaml.safe_load((self.brain / "wooju-brain.yaml").read_text("utf-8")) or {}
                value = str((data.get("content") or {}).get("language") or "auto").strip()
                if value.lower() != "auto":
                    return resolve_language(value)
            except (OSError, yaml.YAMLError, AttributeError):
                pass
        return None

    def content_language(self, text: str | None = None) -> str:
        """The language to write in: the note's own (``text``), else the app's."""
        fixed = self.fixed_content_language()
        if fixed:
            return fixed
        return (detect_language(text) if text else None) or self.language()

    def provider(self) -> Provider:
        if self.provider_override is not None:
            return self.provider_override
        ai = app_settings.load().ai
        if ai.provider == "ollama":
            return OllamaProvider(ai.model or recommended_ollama_model(), host=ai.ollama_host)
        key = app_settings.get_api_key(ai.provider)
        if not key:
            raise LLMError("missing key", "llm.key_first", retryable=True)
        if ai.provider == "openai":
            return OpenAIProvider(key, model=ai.model) if ai.model else OpenAIProvider(key)
        return AnthropicProvider(key, model=ai.model) if ai.model else AnthropicProvider(key)

    async def pull_model(self, model: str | None = None) -> None:
        """Download a local model through Ollama in the background (default: the chosen one)."""
        ai = app_settings.load().ai
        name = model or ai.model or recommended_ollama_model()
        if self.pull_state["state"] == "pulling":
            return
        provider = OllamaProvider(name, host=ai.ollama_host)
        self.pull_state = {"model": name, "state": "pulling", "message": None}

        async def run() -> None:
            try:
                await asyncio.to_thread(provider.pull)
                self.pull_state["state"] = "done"
                await self.retry_waiting()
                await self.refresh_vectors()
                await self.poll_icloud()
            except LLMError as exc:
                self.pull_state.update(state="failed", message=exc.localized(self.language()))

        asyncio.create_task(run())

    # -------------------------------------------------------------- writes

    def _require_brain(self) -> Path:
        if self.brain is None:
            raise SetupError("setup.brain_first")
        return self.brain

    async def _apply_own(self, path: str, content: str, title: str) -> Proposal:
        """Apply a change the user made by clicking (their click is the approval)."""
        proposal = Proposal(
            agent="you",
            origin=path,
            title=title,
            changes=[FileChange(op="write", path=path, content=content)],
            approval="auto",
        )
        self.store.save(proposal)
        return await self.apply(proposal)

    async def apply(self, proposal: Proposal) -> Proposal:
        brain = self._require_brain()
        async with self.lock:
            result = await asyncio.to_thread(apply_proposal, brain, proposal, self.store)
            await asyncio.to_thread(self.index.scan, brain)
        return result

    async def reject(self, proposal: Proposal) -> Proposal:
        async with self.lock:
            return reject_proposal(proposal, self.store)

    async def undo(self, commit_id: str) -> str:
        brain = self._require_brain()
        async with self.lock:
            sha = await asyncio.to_thread(history.undo, brain, commit_id)
            await asyncio.to_thread(self.index.scan, brain)
        return sha
