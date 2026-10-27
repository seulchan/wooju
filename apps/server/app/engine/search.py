"""Search by meaning, Ask, and the Challenger."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from brain_core.changes import (
    Proposal,
    data_dir,
)
from brain_core.retrieve import Retriever
from brain_core.vectors import VectorCache
from wooju_agents.ask import Answer, ask
from wooju_agents.challenge import challenge_insight, challenge_query
from wooju_agents.embed import EMBED_MODEL, Embedder
from wooju_agents.llm import (
    LLMError,
)

from .. import settings as app_settings
from .base import (
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
