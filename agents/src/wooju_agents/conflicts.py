"""Conflict check: does a new source disagree with what the Brain already holds?

Run once when a source is organized. The new note is compared with the most
related passages from other sources and knowledge notes; the model reports
only direct factual disagreements (a different number, date, rule, or fact
about the same thing at the same time). Each report must point to a passage,
which is checked in code. Results are written into the new note as a
``## Conflicts`` section linking the other note, and shown on Home until the
user marks them checked. Nothing else is changed: deciding which is right is
the user's call (edit or retire one of them).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Annotated

from pydantic import BaseModel, Field, ValidationError

from brain_core.retrieve import Passage

from .llm import Provider
from .text import normalize_korean

SECTION = "Conflicts"
_LANGUAGE_NAME = {"ko": "Korean", "en": "English"}
_PASSAGE_CHARS = 700


class ConflictItem(BaseModel):
    new_claim: str = Field(description="What the new source says, briefly.")
    existing: int = Field(description="Number of the passage it conflicts with.")
    existing_claim: str = Field(description="What that passage says instead, briefly.")


class ConflictDraft(BaseModel):
    conflicts: Annotated[list[ConflictItem], Field(max_length=3)] = Field(default_factory=list)


_SYSTEM = (
    "You compare a new source note with numbered passages from a personal research notebook. "
    "Report only direct factual contradictions: the same thing, at the same time, stated "
    "differently (a different number, date, deadline, rule, or fact). Not contradictions: "
    "different topics, different time periods or dates (a rate in July and another in August), "
    "one source having more detail, opinions or forecasts that differ, or uncertainty. "
    "If there is no clear contradiction, return an empty list. Most notes have none. "
    "Write new_claim and existing_claim in {language}."
)


@dataclass
class Conflict:
    new_claim: str
    existing_claim: str
    passage: Passage


def find_conflicts(
    note_body: str, passages: list[Passage], provider: Provider, *, language: str
) -> list[Conflict]:
    if not passages:
        return []
    blocks = []
    for n, p in enumerate(passages, 1):
        text = p.text.strip()[:_PASSAGE_CHARS]
        date = p.record.metadata.get("published") or ""
        where = p.record.title + (f" — {p.heading}" if p.heading else "")
        blocks.append(f"[{n}] {where}{f' ({date})' if date else ''}\n{text}")
    user = f"New source note:\n{note_body.strip()[:3000]}\n\nPassages:\n\n" + "\n\n".join(blocks)
    system = _SYSTEM.format(language=_LANGUAGE_NAME.get(language, "English"))
    result = provider.generate_json(system, user, ConflictDraft.model_json_schema())
    try:
        draft = ConflictDraft.model_validate(result.data)
    except ValidationError:
        return []
    out: list[Conflict] = []
    seen: set[str] = set()
    for item in draft.conflicts:
        if not 1 <= item.existing <= len(passages):
            continue  # must point at a passage that was shown
        passage = passages[item.existing - 1]
        if passage.id in seen or not item.new_claim.strip() or not item.existing_claim.strip():
            continue
        seen.add(passage.id)
        out.append(Conflict(item.new_claim.strip(), item.existing_claim.strip(), passage))
    return out


_LABELS = {
    "ko": ("이 자료", "다른 노트"),
    "en": ("This source", "Other note"),
}


def render_section(conflicts: list[Conflict], *, note_path: str, language: str) -> str:
    this, other = _LABELS.get(language, _LABELS["en"])
    fix = normalize_korean if language == "ko" else (lambda s: s)
    lines = [f"## {SECTION}", ""]
    for c in conflicts:
        rel = os.path.relpath(c.passage.record.path, os.path.dirname(note_path) or ".")
        link = f"[{c.passage.record.title}]({PurePosixPath(rel).as_posix()})"
        lines.append(f"- {this}: {fix(c.new_claim)} / {other} ({link}): {fix(c.existing_claim)}")
    return "\n".join(lines) + "\n"


def add_section(note: str, section: str) -> str:
    """Put the Conflicts section before the note's links to the original, if any."""
    m = re.search(r"^##\s+(원본|Original)\s*$", note, re.M)
    if m:
        return note[: m.start()] + section + "\n" + note[m.start() :]
    return note.rstrip("\n") + "\n\n" + section


def first_conflict(body: str) -> str | None:
    """The first line of a note's Conflicts section, for Home."""
    m = re.search(rf"^##\s+{SECTION}\s*$(.*?)(?=^##\s|\Z)", body, re.M | re.S)
    if not m:
        return None
    for line in m.group(1).splitlines():
        if line.strip().startswith("- "):
            text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line.strip()[2:])
            return text if len(text) <= 160 else text[:159] + "…"
    return None
