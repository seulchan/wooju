"""Search by meaning, Ask, and the Challenger."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from brain_core.changes import (
    Proposal,
    data_dir,
)
from brain_core.retrieve import DUPLICATE_MIN, Passage, Retriever, is_link_list, passages
from brain_core.vectors import VectorCache, normalize
from wooju_agents.ask import Answer, ask
from wooju_agents.challenge import challenge_insight, challenge_query
from wooju_agents.embed import EMBED_MODEL, Embedder
from wooju_agents.llm import (
    LLMError,
)

from .. import settings as app_settings
from .base import (
    SetupError,
    logger,
)


class SearchMixin:
    """Part of :class:`app.engine.Engine`; uses its state (``self.brain``, ``self.index``...)."""

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
            await self._sweep_if_changed()
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
                await self._sweep_if_changed()
            except LLMError:
                logger.warning("Meaning search indexing paused; keyword search still works")
                self.search_state["state"] = "off"

        self._embedding = asyncio.create_task(run(), name="wooju-embed")

    async def _sweep_if_changed(self) -> None:
        """Let the topics agent file new notes, once per index version."""
        if self._swept_at == self.index.indexed_at or self._sweeping:
            return
        if (await self.retriever()).pending:
            return  # some notes have no vector yet: filing them now would skip them for good
        self._sweeping = True
        try:
            await self.sweep_topics()
        except Exception:  # noqa: BLE001 — filing is a convenience; search still works
            logger.exception("Filing notes into topics failed")
        finally:
            self._sweeping = False
        # Marked done only now, after any change the pass made has been applied.
        self._swept_at = self.index.indexed_at

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

    async def _quick_vector(self, text: str, wait: float = 2.0) -> Any:
        """The query's embedding if the AI is free within ``wait`` seconds, else None.

        Search must not sit behind a file being organized: when the AI is busy,
        it answers with keyword search alone.
        """
        if self.search_state.get("state") not in ("ready", "indexing"):
            return None
        try:
            await asyncio.wait_for(self.ai_lane.acquire(), wait)
        except TimeoutError:
            return None
        try:
            return await self.query_vector(text)
        finally:
            self.ai_lane.release()

    async def find(self, query: str, limit: int = 40) -> tuple[list[tuple[float, Passage]], bool]:
        """Notes for the search page, by keyword and (when available) by meaning.

        Returns the best passage of each note and whether meaning search was used.
        """
        self._require_brain()
        retriever = await self.retriever()
        vec = await self._quick_vector(query)
        hits = await asyncio.to_thread(retriever.search_notes, query, limit, vec)
        return hits, vec is not None

    async def related(self, record_id: str) -> dict[str, Any]:
        """What a note links to, what links to it, and notes close in meaning."""
        record = self.index.get(record_id)
        if record is None:
            raise SetupError("review.not_found")

        def ref(r: Any, **extra: Any) -> dict[str, Any]:
            return {
                "id": r.id,
                "title": r.title,
                "category": r.category,
                "status": r.status,
                **extra,
            }

        out_ids = [link.resolved_id for link in record.links if link.resolved_id]
        out_ids += [d.resolved_id for d in record.derived_from_resolved if d.resolved_id]
        links_out = [
            ref(r)
            for r in (self.index.get(i) for i in dict.fromkeys(out_ids))
            if r is not None and r.id != record_id and r.category != "other"
        ]
        links_in = []
        for other in self.index.all_records():
            if other.id == record_id or other.category == "other":
                continue
            targets = {link.resolved_id for link in other.links}
            targets |= {d.resolved_id for d in other.derived_from_resolved}
            if record_id in targets:
                links_in.append(ref(other))
        links_in.sort(key=lambda r: (r["category"], r["title"]))
        linked = {r["id"] for r in links_out} | {r["id"] for r in links_in}
        retriever = await self.retriever()
        near = await asyncio.to_thread(retriever.similar, record_id, 8)
        similar = [
            ref(r, score=round(score, 3), duplicate=score >= DUPLICATE_MIN)
            for score, r in near
            if r.id not in linked and not r.retired
        ][:6]
        return {"links_out": links_out, "links_in": links_in, "similar": similar}

    async def near_duplicates(self, record_id: str) -> list[dict[str, str]]:
        """Existing notes that say nearly the same as a newly saved one.

        Embeds the new note now (and keeps the vectors, so indexing later skips
        it). Best effort: empty when meaning search is off or the AI is busy.
        """
        if self.search_state.get("state") not in ("ready", "indexing"):
            return []
        record = self.index.get(record_id)
        if record is None:
            return []
        texts = [p.embedding_text() for p in passages(record) if not is_link_list(p.text)]
        if not texts:
            return []
        embedder, cache = self.embedder(), self.vector_cache()
        try:
            async with self.ai_lane:
                vectors = await asyncio.to_thread(embedder.documents, texts)
        except LLMError:
            return []
        await asyncio.to_thread(
            cache.put_many, [(cache.key(t), v) for t, v in zip(texts, vectors, strict=True)]
        )
        unit = [list(normalize(v)) for v in vectors]
        mean = [sum(col) / len(unit) for col in zip(*unit, strict=True)]
        norm = sum(x * x for x in mean) ** 0.5 or 1.0
        retriever = await self.retriever()
        near = await asyncio.to_thread(
            retriever.similar, record_id, 3, DUPLICATE_MIN, [x / norm for x in mean]
        )
        return [{"id": r.id, "title": r.title} for _, r in near if not r.retired]

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
