"""The running app: which Brain is open, its index, the ingest queue, and writes.

All writes to a Brain go through :class:`Engine` and are serialized by one lock,
so the ingest worker and the user's approvals never interleave. Every write ends
with a rescan, so the UI reflects the change even when file watching is off.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import re
import shutil
import uuid
from collections.abc import AsyncIterator
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

import yaml

from brain_core import history
from brain_core.changes import (
    FileChange,
    Proposal,
    ProposalError,
    ProposalStore,
    apply_proposal,
    data_dir,
    reject_proposal,
)
from brain_core.index import BrainIndex
from brain_core.markdown import replace_body, set_frontmatter_value, split_frontmatter
from brain_core.messages import UserFacingError, render
from brain_core.retrieve import Retriever, RetrieverCache
from brain_core.vectors import VectorCache
from wooju_agents.ask import Answer, ask
from wooju_agents.capture import (
    LINK_SUFFIXES,
    CaptureError,
    classify_text,
    link_for,
    read_link_file,
    save_link,
    save_memo,
)
from wooju_agents.challenge import challenge_insight, challenge_query
from wooju_agents.conflicts import add_section, find_conflicts, render_section
from wooju_agents.embed import EMBED_MODEL, Embedder
from wooju_agents.ingest import IngestError, inbox_files, ingest_file
from wooju_agents.llm import (
    AnthropicProvider,
    LLMError,
    OllamaProvider,
    OpenAIProvider,
    Provider,
    recommended_ollama_model,
)
from wooju_agents.questions import Question, make_questions
from wooju_agents.text import ACCEPTED_SUFFIXES, detect_language, resolve_language

from . import icloud, notes, telegram
from . import settings as app_settings
from .config import resolve_brain_path, watch_enabled
from .watcher import watch_and_refresh

logger = logging.getLogger("wooju")

JobState = Literal["queued", "working", "waiting", "done", "failed"]
RETRY_SECONDS = 10.0
MAX_ATTEMPTS = 3


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
    attempts: int = 0  # tries that ended because the AI wasn't available
    conflicts: int = 0  # disagreements with existing notes, written into the note
    note_id: str | None = None  # the source note it became (for the user's one line)
    title: str | None = None  # what it was saved as (or the existing note, if a duplicate)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def template_dir() -> Path:
    override = os.environ.get("WOOJU_TEMPLATE_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    return Path(__file__).resolve().parents[3] / "template"


def samples_dir() -> Path:
    """Sample notes to look around with, one folder per language (``samples/<lang>``)."""
    override = os.environ.get("WOOJU_SAMPLES_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    return Path(__file__).resolve().parents[3] / "samples"


SAMPLE_TAG = "sample"


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
        if suffix.lower() not in ACCEPTED_SUFFIXES:
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

    def saved_source_for(self, *urls: str | None) -> Any:
        """The source note already saved from one of these addresses, if any."""
        wanted = {u.rstrip("/") for u in urls if u}
        for record in self.index.sources():
            ref = record.metadata.get("canonical_ref")
            if isinstance(ref, str) and ref.rstrip("/") in wanted:
                return record
        return None

    def pending_link_file(self, url: str) -> str | None:
        """An inbox file already fetched from ``url`` and not organized yet."""
        brain = self._require_brain()
        inbox = brain / "inbox"
        for path in inbox.glob("*") if inbox.is_dir() else []:
            rel = path.relative_to(brain).as_posix()
            if path.is_file() and link_for(brain, rel) in (url, url.rstrip("/")):
                return rel
        return None

    async def receive_text(self, text: str, *, via: str) -> dict[str, Any]:
        """A link or memo from the app, iCloud, or Telegram.

        A link is fetched into the inbox and queued like a dropped file; a memo
        is saved as written. Raises CaptureError (shown to the user).
        """
        brain = self._require_brain()
        kind, value = classify_text(text)
        if kind == "link":
            existing = self.saved_source_for(value)
            if existing is not None:
                return {"kind": "link", "url": value, "duplicate": True, "title": existing.title}
            pending = self.pending_link_file(value)
            if pending is not None:  # fetched before and not organized yet: try again
                job = await self.enqueue(pending)
                return {"kind": "link", "file": pending, "url": value, "job": job.to_dict()}
            rel = await asyncio.to_thread(save_link, brain, value)
            async with self.lock:
                await asyncio.to_thread(
                    history.commit_paths, brain, [rel, "inbox/.links.json"], f"Received {value}"
                )
            job = await self.enqueue(rel)
            return {"kind": "link", "file": rel, "url": value, "job": job.to_dict()}
        async with self.lock:
            rel = await asyncio.to_thread(save_memo, brain, value, via=via)
            await asyncio.to_thread(history.commit_paths, brain, [rel], f"Memo: {Path(rel).stem}")
            await asyncio.to_thread(self.index.scan, brain)
        return {"kind": "memo", "file": rel}

    def _log_capture(self, via: str, kind: str, name: str, message: str | None = None) -> None:
        entry = {
            "via": via,
            "kind": kind,
            "name": name,
            "message": message,
            "at": datetime.now(UTC).isoformat(),
        }
        self.capture_log = [entry, *self.capture_log][:20]

    async def poll_icloud(self) -> int:
        """Take finished files from iCloud Drive/Wooju Inbox. Returns how many."""
        if self.brain is None or not app_settings.load().capture.icloud:
            return 0
        folder = icloud.capture_folder()
        files = await asyncio.to_thread(self.icloud_watch.ready, folder)
        taken = 0
        for path in files:
            try:
                text = await asyncio.to_thread(icloud.short_text, path)
                if text is not None:
                    result = await self.receive_text(text, via="icloud")
                    self._log_capture("icloud", result["kind"], path.name)
                elif path.suffix.lower() in ACCEPTED_SUFFIXES:
                    data = await asyncio.to_thread(path.read_bytes)
                    rel = await self.receive(path.name, data)
                    await self.enqueue(rel)
                    self._log_capture("icloud", "file", path.name)
                else:
                    await asyncio.to_thread(icloud.set_aside, path)
                    self._log_capture(
                        "icloud",
                        "refused",
                        path.name,
                        render("upload.unsupported", self.language(), name=path.name),
                    )
                    continue
            except UserFacingError as exc:
                await asyncio.to_thread(icloud.set_aside, path)
                self._log_capture("icloud", "refused", path.name, exc.localized(self.language()))
                continue
            path.unlink(missing_ok=True)
            taken += 1
        return taken

    async def check_conflicts(self, path: str, content: str, provider: Provider) -> tuple[int, str]:
        """Compare a new source note with related notes.

        Returns ``(number of conflicts, note content)`` with a Conflicts section
        added when there are any. Best effort: any failure returns the note as is.
        """
        try:
            body = split_frontmatter(content)[1]
            retriever = await self.retriever()
            async with self.ai_lane:
                query_vec = await self.query_vector(body[:1500])
                hits = await asyncio.to_thread(retriever.search, body[:1500], 8, 1, query_vec)
                passages = [p for _, p in hits if p.record.category in ("source", "knowledge")][:6]
                conflicts = await asyncio.to_thread(
                    find_conflicts, body, passages, provider, language=self.content_language(body)
                )
        except Exception:  # noqa: BLE001 — the check is extra; saving the source is not
            logger.exception("Conflict check failed for %s", path)
            return 0, content
        if not conflicts:
            return 0, content
        section = render_section(conflicts, note_path=path, language=self.content_language(body))
        return len(conflicts), add_section(content, section)

    async def retry_job(self, job_id: str) -> Job:
        job = self.jobs.get(job_id)
        if job is None:
            raise SetupError("job.gone")
        job.state, job.message, job.attempts = "queued", None, 0
        await self.queue.put(job)
        return job

    async def discard_job(self, job_id: str) -> Job:
        """Remove a failed file from the inbox (recorded, so it can be undone)."""
        brain = self._require_brain()
        job = self.jobs.get(job_id)
        if job is None or job.state in ("queued", "working"):
            raise SetupError("job.gone")
        async with self.lock:
            (brain / job.file).unlink(missing_ok=True)
            await asyncio.to_thread(
                history.commit_paths, brain, [job.file], f"Removed {Path(job.file).name}"
            )
        del self.jobs[job_id]
        return job

    # ----------------------------------------------------------- telegram

    async def start_telegram(self) -> None:
        """Start (or restart) listening to the user's bot, if it is set up."""
        if self.telegram_task is not None:
            self.telegram_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self.telegram_task
            self.telegram_task = None
        if not app_settings.load().capture.telegram:
            return
        token = app_settings.get_api_key(telegram.KEY_NAME)
        if not token:
            return
        bot = self.telegram_factory(token)
        self.telegram_task = asyncio.create_task(self._telegram_loop(bot), name="wooju-telegram")

    async def _telegram_loop(self, bot: Any) -> None:
        state = telegram.load_state()
        offset = state.get("offset")
        if self.telegram_bot_name is None:
            with contextlib.suppress(telegram.TelegramError):
                self.telegram_bot_name = (await asyncio.to_thread(bot.me)).get("username")
        while True:
            try:
                updates = await asyncio.to_thread(bot.updates, offset)
            except telegram.TelegramError as exc:
                logger.info("Telegram unreachable (%s); retrying", exc)
                await asyncio.sleep(15)
                continue
            for update in updates:
                offset = update["update_id"] + 1
                telegram.save_state({"offset": offset})
                message = update.get("message")
                if message:
                    try:
                        await self._telegram_message(bot, message)
                    except Exception:  # noqa: BLE001 — one message must not stop the bot
                        logger.exception("Telegram message failed")

    def _say(self, key: str, **params: Any) -> str:
        return render(key, self.language(), **params)

    async def _telegram_message(self, bot: Any, message: dict[str, Any]) -> None:
        chat_id = message["chat"]["id"]
        text = (message.get("text") or message.get("caption") or "").strip()
        settings = app_settings.load()
        paired = settings.capture.telegram_chat_id
        send = lambda key, **p: asyncio.to_thread(bot.send, chat_id, self._say(key, **p))  # noqa: E731

        if paired is None:
            if telegram.pairing_code_in(text) == self.telegram_pair_code:
                settings.capture.telegram_chat_id = chat_id
                app_settings.save(settings)
                self.telegram_pair_code = telegram.new_pairing_code()
                await send("telegram.paired")
            else:
                await send("telegram.pair_first")
            return
        if chat_id != paired:
            await send("telegram.private")
            return
        if self.brain is None:
            await send("setup.brain_first")
            return

        try:
            if message.get("document"):
                doc = message["document"]
                name = doc.get("file_name") or "file"
                data = await asyncio.to_thread(bot.download, doc["file_id"])
                rel = await self.receive(name, data)
                job = await self.enqueue(rel)
                self._log_capture("telegram", "file", name)
                await send("telegram.received", name=name)
                asyncio.create_task(self._telegram_follow(bot, chat_id, job))
            elif message.get("photo"):
                await send("telegram.no_photos")
            elif text.startswith("/"):
                await send("telegram.help")
            elif text:
                result = await self.receive_text(text, via="telegram")
                self._log_capture("telegram", result["kind"], text[:40])
                if result["kind"] == "memo":
                    await send("telegram.memo")
                elif result.get("duplicate"):
                    await send("job.duplicate", title=result["title"])
                else:
                    await send("telegram.link")
                    job = self.jobs.get(result["job"]["id"])
                    if job:
                        asyncio.create_task(self._telegram_follow(bot, chat_id, job))
        except UserFacingError as exc:
            await asyncio.to_thread(bot.send, chat_id, exc.localized(self.language()))
        except telegram.TelegramError:
            await send("telegram.download_failed")

    async def _telegram_follow(self, bot: Any, chat_id: int, job: Job, wait: float = 2.0) -> None:
        """Tell the chat how a captured item turned out."""
        told_waiting = False
        for _ in range(int(3600 / wait)):
            if job.state == "done":
                if job.proposal_id is None:  # e.g. already saved before
                    text = job.message or self._say("telegram.saved", title=job.title or job.file)
                else:
                    text = self._say("telegram.saved", title=job.title or job.file)
                    if job.conflicts:
                        text += "\n" + self._say("job.conflicts", count=job.conflicts)
                await asyncio.to_thread(bot.send, chat_id, text)
                return
            if job.state == "failed":
                text = self._say("telegram.failed", error=job.message or job.file)
                await asyncio.to_thread(bot.send, chat_id, text)
                return
            if job.state == "waiting" and not told_waiting:
                told_waiting = True
                await asyncio.to_thread(
                    bot.send, chat_id, job.message or self._say("telegram.waiting")
                )
            await asyncio.sleep(wait)

    async def _open_link_file(self, job: Job) -> bool:
        """Replace a .webloc/.url in the inbox with the page it points to."""
        brain = self._require_brain()
        try:
            url = await asyncio.to_thread(read_link_file, brain / job.file)
            rel = await asyncio.to_thread(save_link, brain, url)
        except CaptureError as exc:
            job.state, job.message = "failed", exc.localized(self.language())
            return False
        async with self.lock:
            (brain / job.file).unlink(missing_ok=True)
            await asyncio.to_thread(
                history.commit_paths,
                brain,
                [job.file, rel, "inbox/.links.json"],
                f"Received {url}",
            )
        job.file = rel
        return True

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
                await self.refresh_vectors()
                await self.poll_icloud()
            except Exception:  # noqa: BLE001
                logger.exception("Background check failed")

    async def enqueue(self, rel: str) -> Job:
        for job in self.jobs.values():
            if job.file != rel:
                continue
            if job.state in ("queued", "working"):
                return job
            if job.state == "waiting":  # asked again: try now instead of waiting
                job.state, job.message = "queued", None
                await self.queue.put(job)
                return job
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
        if Path(job.file).suffix.lower() in LINK_SUFFIXES and not await self._open_link_file(job):
            return
        url = link_for(brain, job.file)
        existing = self.saved_source_for(url) if url else None
        if existing is not None:
            # Already in the Brain from the same address: don't save it twice.
            async with self.lock:
                (brain / job.file).unlink(missing_ok=True)
                await asyncio.to_thread(
                    history.commit_paths,
                    brain,
                    [job.file],
                    f"Removed duplicate {Path(job.file).name}",
                )
            job.state, job.title = "done", existing.title
            job.message = render("job.duplicate", self.language(), title=existing.title)
            return
        try:
            provider = self.provider()
            async with self.ai_lane:
                proposal = await asyncio.to_thread(
                    ingest_file,
                    brain,
                    job.file,
                    provider,
                    language=self.fixed_content_language(),  # None: the material's own
                    ui_language=self.language(),
                )
        except LLMError as exc:
            if exc.retryable:
                job.attempts += 1
                if exc.key == "llm.busy" and job.attempts >= MAX_ATTEMPTS:
                    job.state, job.message = "failed", render("job.gave_up", self.language())
                elif exc.key == "llm.busy":
                    job.state, job.message = "waiting", exc.localized(self.language())
                else:
                    job.state, job.message = "waiting", render("job.waiting", self.language())
            else:
                job.state, job.message = "failed", exc.localized(self.language())
            return
        except IngestError as exc:
            job.state, job.message = "failed", exc.localized(self.language())
            return
        note = next((c for c in proposal.changes if c.path.startswith("sources/")), None)
        if note is not None and note.content:
            count, note.content = await self.check_conflicts(note.path, note.content, provider)
            job.conflicts = count
            job.note_id = note.path.removesuffix(".md")
        self.store.save(proposal)
        job.proposal_id = proposal.id
        saved_title = split_frontmatter(note.content or "")[0].get("title") if note else None
        job.title = str(saved_title) if saved_title else proposal.title
        if job.conflicts:
            job.message = render("job.conflicts", self.language(), count=job.conflicts)
        if proposal.approval == "auto":
            proposal = await self.apply(proposal)
            if proposal.status != "applied":
                job.state, job.message = "failed", render("job.invalid", self.language())
                return
        job.state = "done"

    # ------------------------------------------------------- ask, challenge

    def embedder(self) -> Embedder:
        if self.embedder_override is not None:
            return self.embedder_override
        return Embedder(EMBED_MODEL, host=app_settings.load().ai.ollama_host)

    def vector_cache(self) -> VectorCache:
        return VectorCache(data_dir() / "search" / "vectors.sqlite", EMBED_MODEL)

    async def retriever(self) -> Retriever:
        """The passage retriever for the current index, with cached vectors attached."""
        retriever = await asyncio.to_thread(self.retrievers.get, self.index)
        if retriever.pending is None:
            await asyncio.to_thread(retriever.load_vectors, self.vector_cache())
        return retriever

    async def refresh_vectors(self) -> None:
        """Embed passages that have no vector yet, in the background.

        Runs when the embedding model is available; otherwise search simply
        stays keyword-only. Safe to call often: it does nothing when up to date.
        """
        if self.brain is None or (self._embedding and not self._embedding.done()):
            return
        if any(j.state in ("queued", "working") for j in self.jobs.values()):
            return  # organizing comes first; two models at once can exhaust memory
        embedder = self.embedder()
        if not await asyncio.to_thread(embedder.ready):
            self.search_state = {"state": "off", "done": 0, "total": 0}
            return
        retriever = await self.retriever()
        missing = list(retriever.pending or [])
        done, total = retriever.vector_coverage
        if not missing:
            self.search_state = {"state": "ready", "done": done, "total": total}
            return

        # Set before the task starts, so a status check right now already sees it.
        self.search_state = {"state": "indexing", "done": done, "total": total}

        async def run() -> None:
            cache = self.vector_cache()
            try:
                for start in range(0, len(missing), 32):
                    chunk = missing[start : start + 32]
                    # Small batches, each taking its turn, so a file or a
                    # question never waits long behind indexing.
                    async with self.ai_lane:
                        vectors = await asyncio.to_thread(
                            embedder.documents, [text for _, text in chunk]
                        )
                    await asyncio.to_thread(
                        cache.put_many, [(k, v) for (k, _), v in zip(chunk, vectors, strict=True)]
                    )
                    self.search_state["done"] = min(total, self.search_state["done"] + len(chunk))
                current = await asyncio.to_thread(self.retrievers.get, self.index)
                await asyncio.to_thread(current.load_vectors, cache)
                d, t = current.vector_coverage
                self.search_state = {"state": "ready", "done": d, "total": t}
            except LLMError:
                logger.warning("Meaning search indexing paused; keyword search still works")
                self.search_state["state"] = "off"

        self._embedding = asyncio.create_task(run(), name="wooju-embed")

    async def query_vector(self, text: str) -> Any:
        """The query's embedding, or None (keyword search) if meaning search is off.

        Call it while holding ``ai_lane``.
        """
        if self.search_state.get("state") not in ("ready", "indexing"):
            return None
        try:
            return await asyncio.to_thread(self.embedder().query, text)
        except LLMError:
            return None

    async def ask_preview(self, question: str) -> list[dict[str, Any]]:
        """Notes likely to be read for ``question``, shown while the answer is written.

        Keyword search only: no AI, so it never waits behind other AI work.
        """
        self._require_brain()
        retriever = await self.retriever()
        hits = await asyncio.to_thread(retriever.search, question, 6)
        seen: dict[str, dict[str, Any]] = {}
        for _, p in hits:
            seen.setdefault(
                p.id, {"id": p.id, "title": p.record.title, "category": p.record.category}
            )
        return list(seen.values())

    async def ask(self, question: str) -> Answer:
        """Answer from the Brain. Read-only; raises LLMError/AskError."""
        self._require_brain()
        provider = self.provider()
        retriever = await self.retriever()
        async with self.ai_lane:  # waits for the current step of other AI work
            query_vec = await self.query_vector(question)
            return await asyncio.to_thread(
                ask,
                self.index,
                question,
                provider,
                language=self.language(),
                retriever=retriever,
                query_vec=query_vec,
            )

    async def ask_stream(self, question: str) -> AsyncIterator[Answer]:
        """Like :meth:`ask`, but yields the answer as it grows (``partial`` set),
        ending with the complete one. Errors are raised after the partials."""
        self._require_brain()
        provider = self.provider()
        retriever = await self.retriever()
        loop = asyncio.get_running_loop()
        updates: asyncio.Queue[Answer | BaseException | None] = asyncio.Queue()

        def on_partial(answer: Answer) -> None:
            loop.call_soon_threadsafe(updates.put_nowait, answer)

        async with self.ai_lane:
            query_vec = await self.query_vector(question)

            async def run() -> None:
                try:
                    final = await asyncio.to_thread(
                        ask,
                        self.index,
                        question,
                        provider,
                        language=self.language(),
                        retriever=retriever,
                        query_vec=query_vec,
                        on_partial=on_partial,
                    )
                    updates.put_nowait(final)
                except BaseException as exc:  # noqa: BLE001 — handed to the reader
                    updates.put_nowait(exc)
                updates.put_nowait(None)

            task = asyncio.create_task(run(), name="wooju-ask")
            try:
                while True:
                    item = await updates.get()
                    if item is None:
                        break
                    if isinstance(item, BaseException):
                        raise item
                    yield item
            finally:
                task.cancel()

    async def challenge(self, insight_id: str) -> Proposal:
        """Propose a Challenge section for an insight; the user approves it in Review."""
        brain = self._require_brain()
        provider = self.provider()
        retriever = await self.retriever()
        record = self.index.get(insight_id)
        async with self.ai_lane:
            query_vec = await self.query_vector(challenge_query(record)) if record else None
            proposal = await asyncio.to_thread(
                challenge_insight,
                brain,
                self.index,
                insight_id,
                provider,
                language=self.content_language(record.content if record else None),
                ui_language=self.language(),
                retriever=retriever,
                query_vec=query_vec,
            )
        return self.store.save(proposal)

    # ---------------------------------------------------------------- edits

    async def edit_note(self, record_id: str, body: str, base: str) -> Proposal:
        """Save the user's own edit of a note's body (frontmatter is kept as is).

        ``base`` is the body the user started from; if the file changed since
        (in another app, or by an agent), nothing is overwritten. The edit is
        the user's, so it applies at once, is checked against the Brain's rules,
        and can be undone in History.
        """
        brain = self._require_brain()
        record = self.index.get(record_id)
        if record is None:
            raise SetupError("review.not_found")
        text = (brain / record.path).read_text(encoding="utf-8")
        current = split_frontmatter(text)[1]
        if current.strip() != base.strip():
            raise SetupError("note.changed")
        if not body.strip():
            raise SetupError("note.empty")
        try:
            updated = replace_body(text, body)
        except ValueError as exc:
            raise SetupError("review.unreadable") from exc
        ko = self.language() == "ko"
        proposal = Proposal(
            agent="you",
            origin=record.path,
            title=f"직접 고침: {record.title}" if ko else f"Edited: {record.title}",
            changes=[FileChange(op="write", path=record.path, content=updated)],
            approval="auto",
        )
        self.store.save(proposal)
        return await self.apply(proposal)

    # What "retired" means in each layer's own status, where it has one.
    _RETIRED_STATUS = {"source": "archived", "insight": "rejected", "memory": "historical"}

    async def retire_note(self, record_id: str, reason: str) -> Proposal:
        """Mark a note as wrong or obsolete. It stays in the Brain with the reason,
        is never used as grounds again, and what rests on it is flagged."""
        brain = self._require_brain()
        record = self.index.get(record_id)
        if record is None:
            raise SetupError("review.not_found")
        if not reason.strip():
            raise SetupError("retire.reason")
        text = (brain / record.path).read_text(encoding="utf-8")
        try:
            updated = set_frontmatter_value(text, "retired", date.today().isoformat())
            updated = set_frontmatter_value(
                updated, "retired_reason", json.dumps(reason.strip(), ensure_ascii=False)
            )
            status = self._RETIRED_STATUS.get(record.category)
            if status:
                before = split_frontmatter(text)[0].get("status")
                if before and before != status:
                    updated = set_frontmatter_value(updated, "status_before_retired", str(before))
                updated = set_frontmatter_value(updated, "status", status)
        except ValueError as exc:
            raise SetupError("review.unreadable") from exc
        ko = self.language() == "ko"
        return await self._apply_own(
            record.path, updated, f"폐기: {record.title}" if ko else f"Retired: {record.title}"
        )

    async def restore_note(self, record_id: str) -> Proposal:
        """Undo a retirement: the note counts again, with its earlier status."""
        brain = self._require_brain()
        record = self.index.get(record_id)
        if record is None:
            raise SetupError("review.not_found")
        text = (brain / record.path).read_text(encoding="utf-8")
        frontmatter = split_frontmatter(text)[0]
        try:
            updated = text
            for key in ("retired", "retired_reason", "status_before_retired"):
                updated = set_frontmatter_value(updated, key, None)
            if record.category in self._RETIRED_STATUS:
                before = frontmatter.get("status_before_retired")
                updated = set_frontmatter_value(updated, "status", str(before) if before else None)
        except ValueError as exc:
            raise SetupError("review.unreadable") from exc
        ko = self.language() == "ko"
        return await self._apply_own(
            record.path, updated, f"되살림: {record.title}" if ko else f"Restored: {record.title}"
        )

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

    async def create_note(
        self,
        kind: str,
        title: str,
        body: str,
        grounds: list[str],
        insight_kind: str = "hypothesis",
        recall: bool = True,
    ) -> tuple[str, Proposal]:
        """Save a note the user wrote. A thought must rest on at least one note."""
        brain = self._require_brain()
        if not title.strip():
            raise SetupError("note.title")
        records = [r for r in (self.index.get(g) for g in grounds) if r is not None]
        if kind == "thought" and not records:
            raise SetupError("note.grounds")
        path = notes.note_path(brain, kind, title)
        content = notes.build(
            path=path,
            kind=kind,
            title=title,
            body=body,
            grounds=records,
            insight_kind=insight_kind,
            review_after=(
                date.today() + timedelta(days=notes.FIRST_REVIEW_DAYS) if recall else None
            ),
        )
        ko = self.language() == "ko"
        proposal = await self._apply_own(
            path, content, f"새 노트: {title.strip()}" if ko else f"New note: {title.strip()}"
        )
        return path.removesuffix(".md"), proposal

    # An insight moves one step at a time (SYNTHESIS.md). Rejecting it is
    # "Retire"; superseding it is done by hand.
    _STATUS_STEPS = {
        ("candidate", "provisional"),
        ("provisional", "established"),
        ("established", "provisional"),
        ("provisional", "candidate"),
    }

    async def set_insight_status(self, record_id: str, status: str) -> Proposal:
        """Move an insight one step along its lifecycle (the validator checks the rules)."""
        brain = self._require_brain()
        record = self.index.get(record_id)
        if record is None or record.category != "insight":
            raise SetupError("review.not_found")
        current = record.status or "candidate"
        if (current, status) not in self._STATUS_STEPS:
            raise SetupError("status.step", current=current, status=status)
        text = (brain / record.path).read_text(encoding="utf-8")
        try:
            updated = set_frontmatter_value(text, "status", status)
        except ValueError as exc:
            raise SetupError("review.unreadable") from exc
        ko = self.language() == "ko"
        title = (
            f"상태 변경 {current} → {status}: {record.title}"
            if ko
            else f"Status {current} → {status}: {record.title}"
        )
        return await self._apply_own(record.path, updated, title)

    async def recall(self, record_id: str, rating: str) -> Proposal:
        """The user tried to recall a note before reading it; schedule the next time."""
        brain = self._require_brain()
        record = self.index.get(record_id)
        if record is None:
            raise SetupError("review.not_found")
        previous = record.metadata.get("review_interval")
        days = notes.next_interval(previous if isinstance(previous, int) else None, rating)
        until = date.today() + timedelta(days=days)
        text = (brain / record.path).read_text(encoding="utf-8")
        try:
            updated = set_frontmatter_value(text, "review_after", until.isoformat())
            updated = set_frontmatter_value(updated, "review_interval", str(days))
        except ValueError as exc:
            raise SetupError("review.unreadable") from exc
        ko = self.language() == "ko"
        label = {"good": "잘 기억함", "partial": "일부 기억함", "poor": "거의 못 떠올림"}
        title = (
            f"떠올림({label[rating]}), 다음 {until.isoformat()}: {record.title}"
            if ko
            else f"Recalled ({rating}), next {until.isoformat()}: {record.title}"
        )
        proposal = await self._apply_own(record.path, updated, title)
        if proposal.status == "applied":
            notes.log_recall(brain, record_id, rating)
        return proposal

    async def questions(self, record_id: str) -> list[Question]:
        """Questions to think about a note with (the AI asks; the user answers)."""
        self._require_brain()
        record = self.index.get(record_id)
        if record is None:
            raise SetupError("review.not_found")
        provider = self.provider()
        retriever = await self.retriever()
        query = f"{record.title} {record.content[:1000]}"
        async with self.ai_lane:
            query_vec = await self.query_vector(query)
            hits = await asyncio.to_thread(retriever.search, query, 12, 1, query_vec)
            others: dict[str, Any] = {}
            for _, p in hits:
                if p.id != record.id and p.record.category != "other":
                    others.setdefault(p.id, p.record)
            return await asyncio.to_thread(
                make_questions,
                record,
                list(others.values())[:4],
                provider,
                language=self.content_language(record.content),
            )

    async def reflect(self, record_id: str, question: str, answer: str) -> Proposal:
        """Keep a question the user answered, with their answer, in the note."""
        brain = self._require_brain()
        record = self.index.get(record_id)
        if record is None:
            raise SetupError("review.not_found")
        if not answer.strip() or not question.strip():
            raise SetupError("note.empty")
        current = (brain / record.path).read_text(encoding="utf-8")
        updated = notes.add_reflection(
            current, question, answer, self.content_language(current), date.today()
        )
        ko = self.language() == "ko"
        return await self._apply_own(
            record.path,
            updated,
            f"생각해 봄: {record.title}" if ko else f"Reflected: {record.title}",
        )

    async def set_takeaway(self, record_id: str, text: str) -> Proposal:
        """The user's one line about a note, in their own words."""
        brain = self._require_brain()
        record = self.index.get(record_id)
        if record is None:
            raise SetupError("review.not_found")
        if not text.strip():
            raise SetupError("note.empty")
        current = (brain / record.path).read_text(encoding="utf-8")
        updated = notes.set_takeaway(current, text, self.content_language(current))
        ko = self.language() == "ko"
        return await self._apply_own(
            record.path,
            updated,
            f"내 생각: {record.title}" if ko else f"My takeaway: {record.title}",
        )

    def edit_proposal(self, proposal_id: str, body: str) -> Proposal:
        """Fix what an agent proposed before approving it (its main note's body)."""
        proposal = self.store.get(proposal_id)
        if proposal is None or proposal.status != "pending":
            raise SetupError("proposal.not_found")
        change = next(
            (c for c in proposal.changes if c.op == "write" and c.path.endswith(".md")), None
        )
        if change is None or change.content is None:
            raise SetupError("proposal.not_found")
        if not body.strip():
            raise SetupError("note.empty")
        try:
            change.content = replace_body(change.content, body)
        except ValueError as exc:
            raise SetupError("review.unreadable") from exc
        return self.store.save(proposal)

    # ----------------------------------------------------------- maintainer

    async def set_review_date(self, record_id: str, until: date | None) -> Proposal:
        """The user reviewed a note: move its review date, or clear it.

        The user's click is the approval, so this applies at once (and can be
        undone in History like any other change).
        """
        brain = self._require_brain()
        record = self.index.get(record_id)
        if record is None:
            raise SetupError("review.not_found")
        text = (brain / record.path).read_text(encoding="utf-8")
        try:
            updated = set_frontmatter_value(
                text, "review_after", until.isoformat() if until else None
            )
        except ValueError as exc:
            raise SetupError("review.unreadable") from exc
        ko = self.language() == "ko"
        if until is None:
            title = (
                f"검토 날짜 지움: {record.title}" if ko else f"Review date cleared: {record.title}"
            )
        else:
            title = (
                f"검토함, 다음 검토 {until.isoformat()}: {record.title}"
                if ko
                else f"Reviewed, next review {until.isoformat()}: {record.title}"
            )
        proposal = Proposal(
            agent="you",
            origin=record.path,
            title=title,
            changes=[FileChange(op="write", path=record.path, content=updated)],
            approval="auto",
        )
        self.store.save(proposal)
        return await self.apply(proposal)

    # -------------------------------------------------------------- writes

    # ------------------------------------------------------------- samples

    def sample_notes(self) -> list[Any]:
        """Notes that came with the app (tagged ``sample``), still in the Brain."""
        out = []
        for record in self.index.all_records():
            tags = record.metadata.get("tags")
            if isinstance(tags, list) and SAMPLE_TAG in tags:
                out.append(record)
        return out

    async def add_samples(self) -> Proposal:
        """Put the sample notes into the Brain so there is something to look around."""
        brain = self._require_brain()
        folder = samples_dir() / self.language()
        if not folder.is_dir():
            folder = samples_dir() / "en"
        if not folder.is_dir():
            raise SetupError("setup.broken_install")
        changes = []
        for path in sorted(p for p in folder.rglob("*") if p.is_file()):
            rel = path.relative_to(folder).as_posix()
            if (brain / rel).exists():
                continue  # already there: never overwrite the user's files
            changes.append(FileChange(op="write", path=rel, content=path.read_text("utf-8")))
        if not changes:
            raise SetupError("samples.present")
        ko = self.language() == "ko"
        proposal = Proposal(
            agent="you",
            origin="samples",
            title="예시 노트 추가" if ko else "Added sample notes",
            changes=changes,
            approval="auto",
        )
        self.store.save(proposal)
        return await self.apply(proposal)

    async def remove_samples(self) -> Proposal:
        """Take the sample notes out again (only files still tagged ``sample``)."""
        brain = self._require_brain()
        changes = [FileChange(op="delete", path=r.path) for r in self.sample_notes()]
        for record in self.sample_notes():
            ref = record.metadata.get("canonical_ref")
            if isinstance(ref, str) and ref.startswith("library/") and (brain / ref).is_file():
                changes.append(FileChange(op="delete", path=ref))
        if not changes:
            raise SetupError("samples.none")
        ko = self.language() == "ko"
        proposal = Proposal(
            agent="you",
            origin="samples",
            title="예시 노트 삭제" if ko else "Removed sample notes",
            changes=changes,
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


__all__ = ["Engine", "Job", "ProposalError", "SetupError", "create_or_open_brain"]
