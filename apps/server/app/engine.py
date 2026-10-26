"""The running app: which Brain is open, its index, the ingest queue, and writes.

All writes to a Brain go through :class:`Engine` and are serialized by one lock,
so the ingest worker and the user's approvals never interleave. Every write ends
with a rescan, so the UI reflects the change even when file watching is off.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import re
import shutil
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import yaml

from brain_core import history
from brain_core.changes import (
    Proposal,
    ProposalError,
    ProposalStore,
    apply_proposal,
    reject_proposal,
)
from brain_core.index import BrainIndex
from brain_core.messages import UserFacingError, render
from brain_core.retrieve import RetrieverCache
from wooju_agents.ask import Answer, ask
from wooju_agents.challenge import challenge_insight
from wooju_agents.ingest import IngestError, inbox_files, ingest_file
from wooju_agents.llm import (
    AnthropicProvider,
    LLMError,
    OllamaProvider,
    OpenAIProvider,
    Provider,
    recommended_ollama_model,
)
from wooju_agents.text import SUPPORTED_SUFFIXES, resolve_language

from . import settings as app_settings
from .config import resolve_brain_path, watch_enabled
from .watcher import watch_and_refresh

logger = logging.getLogger("wooju")

JobState = Literal["queued", "working", "waiting", "done", "failed"]
RETRY_SECONDS = 10.0


class SetupError(UserFacingError):
    """A setup or file problem; ``key`` names the user message."""

    def __init__(self, key: str, **params: Any) -> None:
        super().__init__(key, key, **params)


@dataclass
class Job:
    file: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    state: JobState = "queued"
    message: str | None = None
    proposal_id: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def template_dir() -> Path:
    override = os.environ.get("WOOJU_TEMPLATE_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    return Path(__file__).resolve().parents[3] / "template"


def looks_like_brain(path: Path) -> bool:
    return (path / "wooju-brain.yaml").is_file() or (
        (path / "AGENTS.md").is_file() and (path / "wiki").is_dir()
    )


def create_or_open_brain(path: Path) -> bool:
    """Open an existing Brain or create one from the template. Returns True if created."""
    path = path.expanduser()
    if path.exists() and not path.is_dir():
        raise SetupError("setup.not_folder")
    if path.is_dir() and looks_like_brain(path):
        return False
    if path.is_dir() and any(p for p in path.iterdir() if not p.name.startswith(".")):
        raise SetupError("setup.folder_busy")
    template = template_dir()
    if not template.is_dir():
        raise SetupError("setup.broken_install")
    shutil.copytree(template, path, dirs_exist_ok=True, symlinks=True)
    history.ensure_repo(path)
    return True


def _safe_upload_name(name: str) -> str:
    base = Path(name).name.strip().lstrip(".")
    base = re.sub(r"[\x00-\x1f/\\:]", "_", base)
    return base or "file"


class Engine:
    def __init__(self) -> None:
        self.index = BrainIndex()
        self.brain: Path | None = None
        self.store = ProposalStore()
        self.jobs: dict[str, Job] = {}
        self.queue: asyncio.Queue[Job] = asyncio.Queue()
        self.lock = asyncio.Lock()
        self._worker: asyncio.Task[None] | None = None
        self._watcher: asyncio.Task[None] | None = None
        self._retry: asyncio.Task[None] | None = None
        self.retrievers = RetrieverCache()
        self.provider_override: Provider | None = None  # tests
        self.pull_state: dict[str, str | None] = {"model": None, "state": None, "message": None}

    # ------------------------------------------------------------ lifecycle

    async def start(self) -> None:
        path = resolve_brain_path()
        if path is not None and path.is_dir():
            await self.open(path)
        self._worker = asyncio.create_task(self._work(), name="wooju-ingest")
        self._retry = asyncio.create_task(self._retry_loop(), name="wooju-retry")

    async def stop(self) -> None:
        for task in (self._worker, self._watcher, self._retry):
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

    async def choose_brain(self, path: Path) -> bool:
        created = await asyncio.to_thread(create_or_open_brain, path)
        current = app_settings.load()
        current.brain_path = str(path.expanduser().resolve())
        app_settings.save(current)
        await self.open(path.expanduser().resolve())
        return created

    # ------------------------------------------------------------ settings

    def language(self) -> str:
        setting = "auto"
        if self.brain is not None:
            try:
                data = yaml.safe_load((self.brain / "wooju-brain.yaml").read_text("utf-8")) or {}
                setting = (data.get("content") or {}).get("language", "auto")
            except (OSError, yaml.YAMLError, AttributeError):
                pass
        return resolve_language(setting)

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
            except LLMError as exc:
                self.pull_state.update(state="failed", message=exc.localized(self.language()))

        asyncio.create_task(run())

    # --------------------------------------------------------------- inbox

    def _require_brain(self) -> Path:
        if self.brain is None:
            raise SetupError("setup.brain_first")
        return self.brain

    def save_upload(self, name: str, data: bytes) -> str:
        brain = self._require_brain()
        inbox = brain / "inbox"
        inbox.mkdir(exist_ok=True)
        base = _safe_upload_name(name)
        stem, suffix = Path(base).stem, Path(base).suffix
        if suffix.lower() not in SUPPORTED_SUFFIXES:
            raise SetupError("upload.unsupported", name=base)
        target, n = inbox / base, 2
        while target.exists():
            target, n = inbox / f"{stem}-{n}{suffix}", n + 1
        target.write_bytes(data)
        return target.relative_to(brain).as_posix()

    async def receive(self, name: str, data: bytes) -> str:
        """Save an upload into ``inbox/`` and record it in history first.

        Recording the original before ingest means undoing the saved source
        brings the original file back instead of losing it.
        """
        brain = self._require_brain()
        async with self.lock:
            rel = self.save_upload(name, data)
            await asyncio.to_thread(
                history.commit_paths, brain, [rel], f"Received {Path(rel).name}"
            )
        return rel

    def ai_ready(self) -> bool:
        try:
            provider = self.provider()
        except LLMError:
            return False
        if isinstance(provider, OllamaProvider):
            return bool(provider.status()["model_ready"])
        return True

    async def retry_waiting(self) -> int:
        """Re-queue files that were waiting for the AI, if it is ready now."""
        waiting = [j for j in self.jobs.values() if j.state == "waiting"]
        if not waiting or not await asyncio.to_thread(self.ai_ready):
            return 0
        for job in waiting:
            job.state, job.message = "queued", None
            await self.queue.put(job)
        return len(waiting)

    async def _retry_loop(self) -> None:
        while True:
            await asyncio.sleep(RETRY_SECONDS)
            try:
                await self.retry_waiting()
            except Exception:  # noqa: BLE001
                logger.exception("Retry check failed")

    async def enqueue(self, rel: str) -> Job:
        active = {j.file for j in self.jobs.values() if j.state in ("queued", "working", "waiting")}
        if rel in active:
            return next(
                j for j in self.jobs.values() if j.file == rel and j.state in ("queued", "working")
            )
        job = Job(file=rel)
        self.jobs[job.id] = job
        await self.queue.put(job)
        return job

    async def enqueue_inbox(self) -> list[Job]:
        brain = self._require_brain()
        files = inbox_files(brain)
        if files:
            async with self.lock:
                await asyncio.to_thread(
                    history.commit_paths, brain, files, f"Received {len(files)} file(s)"
                )
        return [await self.enqueue(rel) for rel in files]

    async def _work(self) -> None:
        while True:
            job = await self.queue.get()
            try:
                await self._run(job)
            except Exception as exc:  # noqa: BLE001 — one bad file must not stop the queue
                logger.exception("Ingest failed for %s", job.file)
                job.state, job.message = "failed", render("job.failed", self.language(), error=exc)
            finally:
                self.queue.task_done()

    async def _run(self, job: Job) -> None:
        brain = self._require_brain()
        job.state = "working"
        if not (brain / job.file).exists():
            job.state, job.message = "failed", render("job.gone", self.language())
            return
        try:
            provider = self.provider()
            proposal = await asyncio.to_thread(
                ingest_file, brain, job.file, provider, language=self.language()
            )
        except LLMError as exc:
            if exc.retryable:
                job.state, job.message = "waiting", render("job.waiting", self.language())
            else:
                job.state, job.message = "failed", exc.localized(self.language())
            return
        except IngestError as exc:
            job.state, job.message = "failed", exc.localized(self.language())
            return
        self.store.save(proposal)
        job.proposal_id = proposal.id
        if proposal.approval == "auto":
            proposal = await self.apply(proposal)
            if proposal.status != "applied":
                job.state, job.message = "failed", render("job.invalid", self.language())
                return
        job.state = "done"

    # ------------------------------------------------------- ask, challenge

    async def ask(self, question: str) -> Answer:
        """Answer from the Brain. Read-only; raises LLMError/AskError."""
        self._require_brain()
        provider = self.provider()
        retriever = await asyncio.to_thread(self.retrievers.get, self.index)
        return await asyncio.to_thread(
            ask, self.index, question, provider, language=self.language(), retriever=retriever
        )

    async def challenge(self, insight_id: str) -> Proposal:
        """Propose a Challenge section for an insight; the user approves it in Review."""
        brain = self._require_brain()
        provider = self.provider()
        retriever = await asyncio.to_thread(self.retrievers.get, self.index)
        proposal = await asyncio.to_thread(
            challenge_insight,
            brain,
            self.index,
            insight_id,
            provider,
            language=self.language(),
            retriever=retriever,
        )
        return self.store.save(proposal)

    # -------------------------------------------------------------- writes

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


__all__ = ["Engine", "Job", "ProposalError", "SetupError", "create_or_open_brain"]
