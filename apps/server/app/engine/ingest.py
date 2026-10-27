"""The ingest queue: organizing inbox files with the AI, one at a time, with retries."""

from __future__ import annotations

import asyncio
from pathlib import Path

from brain_core import history
from brain_core.markdown import split_frontmatter
from brain_core.messages import render
from wooju_agents.capture import (
    LINK_SUFFIXES,
    CaptureError,
    link_for,
    read_link_file,
    save_link,
)
from wooju_agents.conflicts import add_section, find_conflicts, render_section
from wooju_agents.ingest import IngestError, inbox_files, ingest_file
from wooju_agents.llm import (
    LLMError,
    OllamaProvider,
    Provider,
)

from .base import (
    MAX_ATTEMPTS,
    RETRY_SECONDS,
    Job,
    SetupError,
    logger,
)


class IngestMixin:
    """Part of :class:`app.engine.Engine`; uses its state (``self.brain``, ``self.index``...)."""

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
