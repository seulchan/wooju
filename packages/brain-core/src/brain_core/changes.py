"""Proposals: the only way an agent changes a Brain.

An agent never writes into the Brain. It creates a :class:`Proposal` (stored
outside the Brain). Applying a proposal:

1. checks every path stays inside the Brain's content folders,
2. writes the change,
3. runs the validator and rolls back if the change *introduced* errors,
4. commits exactly the touched paths to git.

Approval level is decided here from what the change touches, never by the agent:

* ``auto``       — sources, library, and inbox clean-up. Applied right away; the
                   user can undo from history.
* ``batch``      — world-knowledge edits in ``wiki/``, projects, and areas.
* ``individual`` — anything in ``memory/``, and any insight above ``candidate``.
"""

from __future__ import annotations

import json
import os
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, Field

from . import history
from .markdown import split_frontmatter
from .validate import validate_brain

Approval = Literal["auto", "batch", "individual"]
Status = Literal["pending", "applied", "rejected", "failed"]

_WRITABLE_ROOTS = {"sources", "library", "wiki", "memory", "projects", "areas", "inbox", "logs"}
_RANK = {"auto": 0, "batch": 1, "individual": 2}
SNAPSHOT_MESSAGE = "Save your own edits"


class ProposalError(Exception):
    """A proposal cannot be applied."""


class FileChange(BaseModel):
    op: Literal["write", "copy", "delete"]
    path: str  # Brain-relative POSIX path of the target
    content: str | None = None  # for "write"
    source: str | None = None  # Brain-relative path to copy from, for "copy"


class Proposal(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    agent: str
    origin: str | None = None  # what triggered it, e.g. "inbox/report.pdf"
    title: str  # card headline, in the user's language
    summary: str = ""  # card body, in the user's language
    changes: list[FileChange]
    approval: Approval = "individual"
    status: Status = "pending"
    commit: str | None = None
    error: str | None = None
    decided_at: str | None = None
    # Only a list of links changed (a topic's notes): not a change in what the
    # note says, so notes resting on it are not asked to be checked again.
    links_only: bool = False


# ----------------------------------------------------------------- policy


def _safe_rel(path: str) -> PurePosixPath:
    rel = PurePosixPath(path)
    if rel.is_absolute() or not rel.parts or ".." in rel.parts:
        raise ProposalError(f"Unsafe path: {path}")
    if any(part.startswith(".") for part in rel.parts):
        raise ProposalError(f"Hidden paths are not allowed: {path}")
    if rel.parts[0] not in _WRITABLE_ROOTS:
        raise ProposalError(f"Agents cannot write to '{rel.parts[0]}/'.")
    return rel


def approval_for(changes: list[FileChange]) -> Approval:
    """The strictest approval any single change needs."""
    level: Approval = "auto"
    for change in changes:
        top = _safe_rel(change.path).parts[0]
        need: Approval = "auto"
        if top == "memory":
            need = "individual"
        elif top in ("wiki", "projects", "areas"):
            need = "batch"
            if change.op == "write" and change.content:
                fm, _ = split_frontmatter(change.content)
                if fm.get("origin") == "synthesis" and fm.get("status") not in (None, "candidate"):
                    need = "individual"
        if _RANK[need] > _RANK[level]:
            level = need
    return level


# ------------------------------------------------------------------ store


def data_dir() -> Path:
    """App data folder outside any Brain (override with ``WOOJU_DATA_DIR``)."""
    override = os.environ.get("WOOJU_DATA_DIR", "").strip()
    return Path(override).expanduser() if override else Path.home() / ".wooju"


class ProposalStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or data_dir()) / "proposals"

    def save(self, proposal: Proposal) -> Proposal:
        self.root.mkdir(parents=True, exist_ok=True)
        tmp = self.root / f".{proposal.id}.tmp"
        tmp.write_text(proposal.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(self.root / f"{proposal.id}.json")
        return proposal

    def get(self, proposal_id: str) -> Proposal | None:
        if not proposal_id.isalnum():
            return None
        path = self.root / f"{proposal_id}.json"
        if not path.exists():
            return None
        return Proposal.model_validate(json.loads(path.read_text(encoding="utf-8")))

    def list(self, status: Status | None = None) -> list[Proposal]:
        if not self.root.exists():
            return []
        items = [
            Proposal.model_validate(json.loads(p.read_text(encoding="utf-8")))
            for p in sorted(self.root.glob("*.json"))
        ]
        items = [p for p in items if status is None or p.status == status]
        return sorted(items, key=lambda p: p.created_at, reverse=True)


# ------------------------------------------------------------------ apply


def _error_keys(brain: Path) -> set[tuple[str, str, str]]:
    return {(i.path, i.code, i.message) for i in validate_brain(brain).errors}


def apply_proposal(brain: Path, proposal: Proposal, store: ProposalStore | None = None) -> Proposal:
    """Apply, validate, and commit a proposal. Never leaves a half-applied Brain."""
    if proposal.status != "pending":
        raise ProposalError(f"Proposal is already {proposal.status}.")
    brain = Path(brain)
    history.ensure_repo(brain)

    rels = [_safe_rel(c.path) for c in proposal.changes]
    for change in proposal.changes:
        if change.op == "write" and change.content is None:
            raise ProposalError(f"Missing content for {change.path}")
        if change.op == "copy":
            if change.source is None or not (brain / _safe_rel(change.source)).is_file():
                raise ProposalError(f"Nothing to copy from {change.source}")

    # Record the files as they are now first. A note written or edited outside
    # Wooju (Obsidian, a text editor) isn't in history yet; without this, undoing
    # the proposal would delete the note or discard the user's own edits.
    existing = [r.as_posix() for r in rels if (brain / r).is_file()]
    if existing:
        history.commit_paths(brain, existing, SNAPSHOT_MESSAGE)

    before = _error_keys(brain)
    backup: dict[PurePosixPath, bytes | None] = {
        rel: (brain / rel).read_bytes() if (brain / rel).exists() else None for rel in rels
    }

    def rollback() -> None:
        for rel, data in backup.items():
            target = brain / rel
            if data is None:
                target.unlink(missing_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)

    try:
        for change, rel in zip(proposal.changes, rels, strict=True):
            target = brain / rel
            if change.op == "delete":
                target.unlink(missing_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            if change.op == "write":
                target.write_text(change.content or "", encoding="utf-8")
            else:
                shutil.copyfile(brain / _safe_rel(change.source or ""), target)
        new_errors = sorted(_error_keys(brain) - before)
        if new_errors:
            rollback()
            proposal.status = "failed"
            proposal.error = "; ".join(f"{p}: {m}" for p, _c, m in new_errors[:5])
        else:
            message = f"{proposal.title}\n\nProposal: {proposal.id}\nAgent: {proposal.agent}"
            if proposal.origin:
                message += f"\nOrigin: {proposal.origin}"
            if proposal.links_only:
                message += f"\n{history.LINKS_ONLY}"
            proposal.commit = history.commit_paths(brain, [r.as_posix() for r in rels], message)
            proposal.status = "applied"
    except OSError as exc:
        rollback()
        proposal.status = "failed"
        proposal.error = str(exc)

    proposal.decided_at = datetime.now(UTC).isoformat()
    if store is not None:
        store.save(proposal)
    return proposal


def reject_proposal(proposal: Proposal, store: ProposalStore | None = None) -> Proposal:
    if proposal.status != "pending":
        raise ProposalError(f"Proposal is already {proposal.status}.")
    proposal.status = "rejected"
    proposal.decided_at = datetime.now(UTC).isoformat()
    if store is not None:
        store.save(proposal)
    return proposal
