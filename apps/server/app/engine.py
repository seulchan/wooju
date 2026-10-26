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
from datetime import UTC, date, datetime
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
from brain_core.markdown import set_frontmatter_value
from brain_core.messages import UserFacingError, render
from brain_core.retrieve import Retriever, RetrieverCache
from brain_core.vectors import VectorCache
from wooju_agents.ask import Answer, ask
from wooju_agents.capture import (
    LINK_SUFFIXES,
    CaptureError,
    classify_text,
    read_link_file,
    save_link,
    save_memo,
)
from wooju_agents.challenge import challenge_insight, challenge_query
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
from wooju_agents.text import ACCEPTED_SUFFIXES, resolve_language

from . import icloud, telegram
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

    async def receive_text(self, text: str, *, via: str) -> dict[str, Any]:
        """A link or memo from the app, iCloud, or Telegram.

        A link is fetched into the inbox and queued like a dropped file; a memo
        is saved as written. Raises CaptureError (shown to the user).
        """
        brain = self._require_brain()
        kind, value = classify_text(text)
        if kind == "link":
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
                proposal = self.store.get(job.proposal_id) if job.proposal_id else None
                title = proposal.title if proposal else job.file
                await asyncio.to_thread(bot.send, chat_id, f"✓ {title}")
                return
            if job.state == "failed":
                await asyncio.to_thread(bot.send, chat_id, f"✗ {job.message or job.file}")
                return
            if job.state == "waiting" and not told_waiting:
                told_waiting = True
                await asyncio.to_thread(bot.send, chat_id, self._say("telegram.waiting"))
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
        if Path(job.file).suffix.lower() in LINK_SUFFIXES and not await self._open_link_file(job):
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
                for start in range(0, len(missing), 64):
                    chunk = missing[start : start + 64]
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
        """The query's embedding, or None (keyword search) if meaning search is off."""
        if self.search_state.get("state") not in ("ready", "indexing"):
            return None
        try:
            return await asyncio.to_thread(self.embedder().query, text)
        except LLMError:
            return None

    async def ask(self, question: str) -> Answer:
        """Answer from the Brain. Read-only; raises LLMError/AskError."""
        self._require_brain()
        provider = self.provider()
        retriever = await self.retriever()
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

    async def challenge(self, insight_id: str) -> Proposal:
        """Propose a Challenge section for an insight; the user approves it in Review."""
        brain = self._require_brain()
        provider = self.provider()
        retriever = await self.retriever()
        record = self.index.get(insight_id)
        query_vec = await self.query_vector(challenge_query(record)) if record else None
        proposal = await asyncio.to_thread(
            challenge_insight,
            brain,
            self.index,
            insight_id,
            provider,
            language=self.language(),
            retriever=retriever,
            query_vec=query_vec,
        )
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
