"""The topics agent: files notes into topics and suggests new ones.

Filing a note into an existing topic is automatic (the agent adds a link in
the topic's own section; the user can take it out, and it stays out).
A new topic is only suggested: the user taps to create it, and the AI then
writes its name and summary. Decided in docs/DECISIONS.md, "Topics".
"""

from __future__ import annotations

import asyncio
import json
from datetime import date
from typing import Any

from brain_core import topics as tp
from brain_core.changes import FileChange, Proposal, data_dir
from brain_core.markdown import add_made_by
from wooju_agents.topics import AGENT, make_topic

from .. import notes
from .base import SetupError

_GROUP_CATEGORIES = ("source", "knowledge", "insight")


def _stats_file():
    return data_dir() / "topics.json"


def load_topic_state() -> dict[str, Any]:
    try:
        data = json.loads(_stats_file().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_topic_state(state: dict[str, Any]) -> None:
    path = _stats_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


def _count(key: str, n: int = 1) -> None:
    state = load_topic_state()
    stats = state.setdefault("stats", {})
    stats[key] = stats.get(key, 0) + n
    _save_topic_state(state)


class TopicsMixin:
    """Part of :class:`app.engine.Engine`; uses its state (``self.brain``, ``self.index``...)."""

    # ------------------------------------------------------------- reading

    def topic_records(self) -> list[Any]:
        return sorted(
            (r for r in self.index.all_records() if tp.is_topic(r)), key=lambda r: r.title
        )

    def topic_members(self, topic: Any) -> list[str]:
        """Ids of the notes a topic gathers: everything its note links to."""
        ids = [link.resolved_id for link in topic.links if link.resolved_id]
        return [i for i in dict.fromkeys(ids) if i != topic.id]

    async def _topic_vectors(self) -> tuple[dict[str, list[float]], dict[str, Any]]:
        retriever = await self.retriever()
        notes_vec = await asyncio.to_thread(retriever._notes)
        vectors: dict[str, list[float]] = {}
        topics: dict[str, Any] = {}
        for t in self.topic_records():
            v = tp.topic_vector(t.id, self.topic_members(t), notes_vec)
            if v is not None:
                vectors[t.id] = v
                topics[t.id] = t
        return vectors, topics

    # ------------------------------------------------------------- filing

    async def file_into_topics(self, record_ids: list[str]) -> list[str]:
        """Add notes to the topics they clearly belong to. Returns topic titles touched.

        Pure computation over stored vectors (no model call), so it never waits
        for the AI. Notes already in a topic, or taken out of one by the user,
        are left alone.
        """
        if self.brain is None:
            return []
        vectors, topics = await self._topic_vectors()
        if not topics:
            return []
        retriever = await self.retriever()
        additions: dict[str, list[Any]] = {}
        for rid in record_ids:
            record = self.index.get(rid)
            if record is None or record.retired or tp.is_topic(record):
                continue
            if record.category not in _GROUP_CATEGORIES:
                continue
            vec = retriever.note_vector(rid)
            if vec is None:
                continue
            for _, tid in tp.match_topics(vec, vectors):
                if rid not in self.topic_members(topics[tid]):
                    additions.setdefault(tid, []).append(record)
        touched = []
        for tid, members in additions.items():
            if await self._add_to_topic(topics[tid], members):
                touched.append(topics[tid].title)
        return touched

    async def _add_to_topic(self, topic: Any, members: list[Any], *, by_user: bool = False) -> bool:
        brain = self._require_brain()
        text = (brain / topic.path).read_text(encoding="utf-8")
        language = self.content_language(text)
        updated, added = tp.add_members(text, topic.path, members, language)
        if updated == text:
            return False
        if added and not by_user:
            updated = add_made_by(
                updated, agent=AGENT, model=None, did="topic link", on=date.today().isoformat()
            )
        ko = self.language() == "ko"
        names = ", ".join(m.title for m in members if m.path in added)
        title = (
            f"주제에 연결: {names} → {topic.title}" if ko else f"Filed {names} under {topic.title}"
        )
        proposal = Proposal(
            agent="you" if by_user else AGENT,
            origin=topic.path,
            title=title,
            changes=[FileChange(op="write", path=topic.path, content=updated)],
            approval="auto",
            links_only=True,
        )
        self.store.save(proposal)
        result = await self.apply(proposal)
        if result.status == "applied" and added and not by_user:
            _count("auto_links", len(added))
        return result.status == "applied"

    async def sweep_topics(self) -> int:
        """File every note that is in no topic yet (after indexing). Returns topics touched."""
        if self.brain is None or not self.topic_records():
            return 0
        in_topics = {m for t in self.topic_records() for m in self.topic_members(t)}
        loose = [
            r.id
            for r in self.index.all_records()
            if r.category in _GROUP_CATEGORIES and not tp.is_topic(r) and r.id not in in_topics
        ]
        return len(await self.file_into_topics(loose))

    # ---------------------------------------------------------- suggestions

    async def topic_suggestions(self) -> list[dict[str, Any]]:
        """Groups of close notes outside every topic, minus those the user waved off."""
        if self.brain is None:
            return []
        retriever = await self.retriever()
        notes_vec = await asyncio.to_thread(retriever._notes)
        exclude = {t.id for t in self.topic_records()}
        exclude |= {m for t in self.topic_records() for m in self.topic_members(t)}
        candidates = {}
        for nid, v in notes_vec.items():
            r = self.index.get(nid)
            if r is not None and r.category in _GROUP_CATEGORIES and not r.retired:
                candidates[nid] = v
        groups = await asyncio.to_thread(tp.emerging, candidates, exclude)
        dismissed = [set(g) for g in load_topic_state().get("dismissed", [])]
        out = []
        for group in groups:
            if any(len(set(group) & d) * 2 >= len(group) for d in dismissed):
                continue
            records = [self.index.get(i) for i in group]
            out.append(
                {
                    "key": "|".join(group),
                    "label": records[0].title,
                    "members": [
                        {"id": r.id, "title": r.title, "category": r.category} for r in records if r
                    ],
                }
            )
        return out

    async def create_topic(self, member_ids: list[str]) -> Proposal:
        """The user tapped "make it a topic": the AI names it and writes the summary."""
        brain = self._require_brain()
        members = [r for r in (self.index.get(i) for i in member_ids) if r is not None]
        if len(members) < 2:
            raise SetupError("topic.too_few")
        language = self.content_language(" ".join(m.content[:400] for m in members))
        provider = self.provider()
        async with self.ai_lane:
            note = await asyncio.to_thread(
                # Links in the summary are relative to the topics folder.
                make_topic,
                members,
                provider,
                language=language,
                path=f"{tp.TOPIC_FOLDER}/_.md",
            )
        path = notes.note_path(brain, "overview", note.title)
        text = f"---\ntitle: {json.dumps(note.title, ensure_ascii=False)}\n---\n{note.body}"
        text, _ = tp.add_members(text, path, members, language)
        text = add_made_by(
            text, agent=AGENT, model=provider.model, did="created", on=date.today().isoformat()
        )
        ko = self.language() == "ko"
        proposal = Proposal(
            agent=AGENT,
            origin=path,
            title=f"새 주제: {note.title}" if ko else f"New topic: {note.title}",
            changes=[FileChange(op="write", path=path, content=text)],
            approval="auto",  # the user's tap is the approval
        )
        self.store.save(proposal)
        result = await self.apply(proposal)
        if result.status == "applied":
            _count("accepted")
        return result

    def dismiss_topic(self, member_ids: list[str]) -> None:
        state = load_topic_state()
        state.setdefault("dismissed", []).append(sorted(member_ids))
        stats = state.setdefault("stats", {})
        stats["dismissed"] = stats.get("dismissed", 0) + 1
        _save_topic_state(state)

    # ---------------------------------------------------------- by the user

    async def remove_from_topic(self, topic_id: str, member_id: str) -> Proposal:
        brain = self._require_brain()
        topic, member = self.index.get(topic_id), self.index.get(member_id)
        if topic is None or member is None or not tp.is_topic(topic):
            raise SetupError("review.not_found")
        text = (brain / topic.path).read_text(encoding="utf-8")
        updated = tp.remove_member(text, topic.path, member.path)
        ko = self.language() == "ko"
        result = await self._apply_own(
            topic.path,
            updated,
            f"주제에서 뺌: {member.title} ← {topic.title}"
            if ko
            else f"Took {member.title} out of {topic.title}",
            links_only=True,
        )
        if result.status == "applied":
            _count("removed")
        return result

    async def add_to_topic(self, topic_id: str, member_id: str) -> bool:
        topic, member = self.index.get(topic_id), self.index.get(member_id)
        if topic is None or member is None or not tp.is_topic(topic):
            raise SetupError("review.not_found")
        brain = self._require_brain()
        text = (brain / topic.path).read_text(encoding="utf-8")
        # Taken out earlier and now put back by hand: forget the exclusion.
        state = tp.read_state(text, topic.path)
        if member.path in state.excluded:
            from brain_core.markdown import set_frontmatter_value

            rest = [p for p in state.excluded if p != member.path]
            text = set_frontmatter_value(
                text, tp.EXCLUDED_KEY, json.dumps(rest, ensure_ascii=False) if rest else None
            )
            (brain / topic.path).write_text(text, encoding="utf-8")
        return await self._add_to_topic(topic, [member], by_user=True)

    async def topic_view(self, topic_id: str) -> dict[str, Any]:
        """A topic's notes grouped by kind, and close notes not in it yet."""
        topic = self.index.get(topic_id)
        if topic is None or not tp.is_topic(topic):
            raise SetupError("review.not_found")
        brain = self._require_brain()
        state = tp.read_state((brain / topic.path).read_text(encoding="utf-8"), topic.path)
        by_agent = {p.removesuffix(".md") for p in state.added}
        members = []
        for mid in self.topic_members(topic):
            r = self.index.get(mid)
            if r is None or r.category == "other":
                continue
            members.append(
                {
                    "id": r.id,
                    "title": r.title,
                    "category": r.category,
                    "status": r.status,
                    "retired": r.retired,
                    "by_agent": r.id in by_agent,
                }
            )
        vectors, _ = await self._topic_vectors()
        candidates: list[dict[str, Any]] = []
        vec = vectors.get(topic_id)
        if vec is not None:
            retriever = await self.retriever()
            near = await asyncio.to_thread(
                retriever.similar, topic_id, 12, tp.CLUSTER_MIN - 0.07, vec
            )
            have = {m["id"] for m in members}
            excluded = {p.removesuffix(".md") for p in state.excluded}
            for score, r in near:
                if r.id in have or r.id in excluded or tp.is_topic(r) or r.retired:
                    continue
                if r.category not in _GROUP_CATEGORIES:
                    continue
                candidates.append(
                    {"id": r.id, "title": r.title, "category": r.category, "score": round(score, 3)}
                )
        return {
            "id": topic.id,
            "title": topic.title,
            "members": members,
            "candidates": candidates[:6],
        }


__all__ = ["TopicsMixin", "load_topic_state"]
