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

JobState = Literal["queued", "working", "done", "failed"]


class SetupError(Exception):
    """Shown to the user as-is."""


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
        raise SetupError("파일이 아니라 폴더를 골라 주세요.")
    if path.is_dir() and looks_like_brain(path):
        return False
    if path.is_dir() and any(p for p in path.iterdir() if not p.name.startswith(".")):
        raise SetupError("이 폴더에는 이미 다른 파일이 있어요. 빈 폴더나 새 폴더를 골라 주세요.")
    template = template_dir()
    if not template.is_dir():
        raise SetupError("앱 설치가 손상됐어요. 앱을 다시 설치해 주세요.")
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
        self.provider_override: Provider | None = None  # tests

    # ------------------------------------------------------------ lifecycle

    async def start(self) -> None:
        path = resolve_brain_path()
        if path is not None and path.is_dir():
            await self.open(path)
        self._worker = asyncio.create_task(self._work(), name="wooju-ingest")

    async def stop(self) -> None:
        for task in (self._worker, self._watcher):
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
            raise LLMError("missing key", "API 키를 먼저 입력해 주세요.")
        if ai.provider == "openai":
            return OpenAIProvider(key, model=ai.model) if ai.model else OpenAIProvider(key)
        return AnthropicProvider(key, model=ai.model) if ai.model else AnthropicProvider(key)

    # --------------------------------------------------------------- inbox

    def _require_brain(self) -> Path:
        if self.brain is None:
            raise SetupError("먼저 저장할 폴더를 골라 주세요.")
        return self.brain

    def save_upload(self, name: str, data: bytes) -> str:
        brain = self._require_brain()
        inbox = brain / "inbox"
        inbox.mkdir(exist_ok=True)
        base = _safe_upload_name(name)
        stem, suffix = Path(base).stem, Path(base).suffix
        if suffix.lower() not in SUPPORTED_SUFFIXES:
            raise SetupError(
                f"'{base}'은(는) 아직 읽을 수 없는 형식이에요. "
                "PDF, 텍스트, HTML 파일을 넣어 주세요."
            )
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

    async def enqueue(self, rel: str) -> Job:
        active = {j.file for j in self.jobs.values() if j.state in ("queued", "working")}
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
                job.state, job.message = "failed", f"정리하지 못했어요: {exc}"
            finally:
                self.queue.task_done()

    async def _run(self, job: Job) -> None:
        brain = self._require_brain()
        job.state = "working"
        if not (brain / job.file).exists():
            job.state, job.message = "failed", "파일이 더 이상 받은 편지함에 없어요."
            return
        try:
            provider = self.provider()
            proposal = await asyncio.to_thread(
                ingest_file, brain, job.file, provider, language=self.language()
            )
        except (IngestError, LLMError) as exc:
            job.state, job.message = "failed", exc.user_message
            return
        self.store.save(proposal)
        job.proposal_id = proposal.id
        if proposal.approval == "auto":
            proposal = await self.apply(proposal)
            if proposal.status != "applied":
                job.state, job.message = "failed", "정리 결과가 규칙에 맞지 않아 저장하지 않았어요."
                return
        job.state = "done"

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
