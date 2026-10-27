"""Thinking with a note: recall, questions, reflections, the one-line takeaway."""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from typing import Any

from brain_core.changes import (
    Proposal,
)
from brain_core.markdown import set_frontmatter_value
from wooju_agents.questions import Question, make_questions

from .. import notes
from .base import (
    SetupError,
)


class ThinkingMixin:
    """Part of :class:`app.engine.Engine`; uses its state (``self.brain``, ``self.index``...)."""

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
