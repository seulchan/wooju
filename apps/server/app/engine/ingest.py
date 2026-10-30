"""The ingest queue: organizing inbox files with the AI, one at a time, with retries."""

from __future__ import annotations

import asyncio
import contextlib
from datetime import date
from pathlib import Path
from typing import Any

from brain_core import history
from brain_core.changes import FileChange, Proposal, approval_for
from brain_core.markdown import add_made_by, split_frontmatter
from brain_core.messages import render
from wooju_agents.capture import (
    LINK_SUFFIXES,
    CaptureError,
    link_for,
    read_link_file,
    save_link,
)
from wooju_agents.conflicts import add_section, find_conflicts, render_section
from wooju_agents.ingest import IngestError, IngestRun, inbox_files
from wooju_agents.llm import (
    LLMError,
    OllamaProvider,
    Provider,
)
from wooju_agents.originals import original_path
from wooju_agents.text import extract_text
from wooju_agents.versions import Changes, compare, retire_earlier
from wooju_agents.versions import add_section as add_version_section
from wooju_agents.versions import section as version_section

from .base import (
    MAX_ATTEMPTS,
    RETRY_SECONDS,
    Job,
    SetupError,
    logger,
)


class IngestMixin:
    """Part of :class:`app.engine.Engine`; uses its state (``self.brain``, ``self.index``...)."""

    async def check_conflicts(
        self, path: str, content: str, provider: Provider, exclude: str | None = None
    ) -> tuple[int, str]:
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
                passages = [
                    p
                    for _, p in hits
                    if p.record.category in ("source", "knowledge") and p.id != exclude
                ][:6]
                conflicts = await asyncio.to_thread(
                    find_conflicts, body, passages, provider, language=self.content_language(body)
                )
        except Exception:  # noqa: BLE001 — the check is extra; saving the source is not
            logger.exception("Conflict check failed for %s", path)
            return 0, content
        if not conflicts:
            return 0, content
        section = render_section(conflicts, note_path=path, language=self.content_language(body))
        updated = add_made_by(
            add_section(content, section),
            agent="conflicts",
            model=provider.model,
            did="conflicts",
            on=date.today().isoformat(),
        )
        return len(conflicts), updated

    def _changes_since(self, earlier: Any, rel: str) -> Changes | None:
        """What changed between a saved source's original and the same address
        fetched again; None if nothing real did (or it can't be compared)."""
        brain = self._require_brain()
        path = original_path(earlier)
        old_text = self.read_original(path) if path else None
        if not old_text:
            return None
        try:
            new_text = extract_text(brain / rel, max_chars=200_000)[0]
        except Exception:  # noqa: BLE001 — unreadable: treat as the same page
            return None
        found = compare(old_text, new_text)
        return found if found.significant else None

    def _as_new_version(
        self, proposal: Proposal, note: Any, earlier: Any, changes: Changes
    ) -> None:
        """Turn an ingest proposal into a new version of ``earlier``: the new note
        says what changed, and the earlier note is retired in its favour."""
        brain = self._require_brain()
        language = self.content_language(note.content or "")
        link = "../" + earlier.path
        note.content = add_version_section(
            note.content or "",
            version_section(
                changes, earlier_title=earlier.title, earlier_link=link, language=language
            ),
        )
        text = (brain / earlier.path).read_text(encoding="utf-8")
        retired = retire_earlier(text, new_path=note.path, today=date.today(), language=language)
        proposal.changes.append(FileChange(op="write", path=earlier.path, content=retired))
        proposal.approval = approval_for(proposal.changes)

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
        self.remember_via(rel, self.via_for(job.file))
        self.forget_via(job.file)
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
        changes: Changes | None = None
        if existing is not None:
            changes = await asyncio.to_thread(self._changes_since, existing, job.file)
        if existing is not None and changes is None:
            # Already in the Brain from the same address, unchanged: don't save it twice.
            async with self.lock:
                (brain / job.file).unlink(missing_ok=True)
                await asyncio.to_thread(
                    history.commit_paths,
                    brain,
                    [job.file],
                    f"Removed duplicate {Path(job.file).name}",
                )
            self.forget_via(job.file)
            job.state, job.title = "done", existing.title
            job.message = render("job.duplicate", self.language(), title=existing.title)
            return
        run: IngestRun | None = None
        try:
            provider = self.provider()
            run = await asyncio.to_thread(
                IngestRun,
                brain,
                job.file,
                provider,
                language=self.fixed_content_language(),  # None: the material's own
                ui_language=self.language(),
                via=self.via_for(job.file),
            )
            # One step (one part of the source) at a time: a question can go in
            # between parts, and a long file shows how far it has got.
            while not run.finished:
                job.progress = {"done": run.done, "total": run.steps} if run.steps > 1 else None
                async with self.ai_lane:
                    await asyncio.to_thread(run.step)
            job.progress = None
            proposal = await asyncio.to_thread(run.proposal)
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
        if existing is not None and changes is not None and note is not None:
            self._as_new_version(proposal, note, existing, changes)
            job.message = render(
                "job.new_version",
                self.language(),
                added=len(changes.added),
                removed=len(changes.removed),
            )
        if note is not None and note.content:
            # A new version is not "in conflict" with the version it replaces.
            count, note.content = await self.check_conflicts(
                note.path, note.content, provider, exclude=existing.id if existing else None
            )
            job.conflicts = count
            job.note_id = note.path.removesuffix(".md")
        self.store.save(proposal)
        if run is not None:
            run.forget()  # saved: the steps are not needed to continue any more
        self.forget_via(job.file)
        job.proposal_id = proposal.id
        saved_title = split_frontmatter(note.content or "")[0].get("title") if note else None
        job.title = str(saved_title) if saved_title else proposal.title
        if job.conflicts:
            conflicts = render("job.conflicts", self.language(), count=job.conflicts)
            job.message = f"{job.message} {conflicts}" if job.message else conflicts
        if proposal.approval == "auto":
            proposal = await self.apply(proposal)
            if proposal.status != "applied":
                job.state, job.message = "failed", render("job.invalid", self.language())
                return
            if job.note_id:
                with contextlib.suppress(Exception):  # a hint; saving already succeeded
                    job.similar = await self.near_duplicates(job.note_id)
                with contextlib.suppress(Exception):  # filing is a convenience too
                    job.topics = await self.file_into_topics([job.note_id])
        job.state = "done"
