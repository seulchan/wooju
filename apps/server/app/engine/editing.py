"""Changes made by clicking: edits, retiring, new notes, status, review dates, samples."""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

from brain_core.changes import (
    FileChange,
    Proposal,
)
from brain_core.markdown import replace_body, set_frontmatter_value, split_frontmatter

from .. import notes
from .base import (
    SAMPLE_TAG,
    SetupError,
    samples_dir,
)


class EditingMixin:
    """Part of :class:`app.engine.Engine`; uses its state (``self.brain``, ``self.index``...)."""

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

    async def retire_note(
        self, record_id: str, reason: str, replaced_by: str | None = None
    ) -> Proposal:
        """Mark a note as wrong or obsolete. It stays in the Brain with the reason,
        is never used as grounds again, and what rests on it is flagged.

        ``replaced_by`` names the note that takes its place, if any: the old
        note then points readers there (``superseded_by``).
        """
        brain = self._require_brain()
        record = self.index.get(record_id)
        if record is None:
            raise SetupError("review.not_found")
        if not reason.strip():
            raise SetupError("retire.reason")
        replacement = self.index.get(replaced_by) if replaced_by else None
        if replaced_by and (
            replacement is None or replacement.id == record_id or replacement.retired
        ):
            raise SetupError("retire.replacement")
        text = (brain / record.path).read_text(encoding="utf-8")
        try:
            updated = set_frontmatter_value(text, "retired", date.today().isoformat())
            if replacement is not None:
                updated = set_frontmatter_value(updated, "superseded_by", replacement.path)
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
            for key in ("retired", "retired_reason", "status_before_retired", "superseded_by"):
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
