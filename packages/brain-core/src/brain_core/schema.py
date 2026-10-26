"""Frontmatter schemas for each Brain layer.

These models turn the prose rules in ``template/docs`` into machine-checkable
contracts. They describe *frontmatter only*; body rules (required sections,
links, secrets) live in :mod:`brain_core.validate`.

Design rules:

* Only what the Brain constitution actually requires is required here.
  "Recommended" fields are optional in the model and reported as warnings by the
  validator, so the schema never forces agents to invent values (MEMORY.md: "Do
  not invent dates merely to satisfy a schema").
* Unknown keys are allowed. Brains grow; the schema must not reject extra
  metadata such as ``aliases`` or ``tags``.
* Controlled vocabularies are closed ``Literal`` sets copied from the docs.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

# --------------------------------------------------------------------------- vocab

SourceType = Literal[
    "paper",
    "book",
    "docs",
    "spec",
    "repo",
    "article",
    "video",
    "podcast",
    "course",
    "conversation",
    "experience",
    "other",
]
SourceStatus = Literal["active", "superseded", "archived"]

InsightKind = Literal["pattern", "connection", "tension", "implication", "hypothesis"]
InsightStatus = Literal["candidate", "provisional", "established", "rejected", "superseded"]

EpistemicStatus = Literal["established", "provisional", "contested"]
EvidenceStrength = Literal["high", "medium", "low"]

MemoryType = Literal[
    "fact",
    "preference",
    "goal",
    "constraint",
    "decision",
    "relationship",
    "routine",
    "other",
]
Provenance = Literal["user_explicit", "user_confirmed", "observed", "imported", "inferred"]
MemoryStatus = Literal["current", "historical", "superseded"]

WIKI_SECTIONS = ("concepts", "overviews", "questions", "how-tos", "mental-models")

# ------------------------------------------------------------------- date helpers

_FULL_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_PARTIAL_DATE = re.compile(r"^\d{4}(-\d{2})?(-\d{2})?$")


def _to_iso_date(value: Any) -> str:
    """Accept a YAML date or an ISO ``YYYY-MM-DD`` string; return the string."""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str) and _FULL_DATE.match(value.strip()):
        date.fromisoformat(value.strip())  # rejects 2026-13-40
        return value.strip()
    raise ValueError("expected a date written as YYYY-MM-DD")


def _to_partial_date(value: Any) -> str:
    """Accept ``YYYY-MM-DD``, ``YYYY-MM``, ``YYYY`` or ``unknown``."""
    if isinstance(value, (date, datetime)):
        return _to_iso_date(value)
    if isinstance(value, int) and 1000 <= value <= 9999:
        return str(value)
    if isinstance(value, str):
        text = value.strip()
        if text == "unknown":
            return text
        if _PARTIAL_DATE.match(text):
            if len(text) == 10:
                date.fromisoformat(text)
            return text
    raise ValueError("expected YYYY-MM-DD, YYYY-MM, YYYY, or 'unknown'")


def _to_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and all(isinstance(v, str) for v in value):
        return value
    raise ValueError("expected a list of strings")


IsoDate = Annotated[str, BeforeValidator(_to_iso_date)]
PartialDate = Annotated[str, BeforeValidator(_to_partial_date)]
StrList = Annotated[list[str], BeforeValidator(_to_str_list)]


class _Frontmatter(BaseModel):
    model_config = ConfigDict(extra="allow")

    title: str | None = None
    aliases: StrList = Field(default_factory=list)
    # Optional review date for fast-decaying knowledge (prices, earnings, plans).
    # The Maintainer surfaces notes whose review date has passed.
    review_after: IsoDate | None = None


# ----------------------------------------------------------------------- layers


class SourceFrontmatter(_Frontmatter):
    """``sources/`` — what one identifiable source says (KNOWLEDGE.md)."""

    source_type: SourceType
    canonical_ref: Annotated[str, Field(min_length=1)]
    authors: StrList = Field(default_factory=list)
    published: PartialDate | None = None
    accessed: IsoDate | None = None
    status: SourceStatus = "active"


class Epistemic(BaseModel):
    """Optional rigorous-mode block (EPISTEMICS.md)."""

    model_config = ConfigDict(extra="allow")

    mode: Literal["standard", "rigorous"] | None = None
    status: EpistemicStatus | None = None
    evidence_strength: EvidenceStrength | None = None
    verified_at: IsoDate | None = None


class WikiFrontmatter(_Frontmatter):
    """``wiki/`` — durable knowledge about the world (KNOWLEDGE.md)."""

    epistemic: Epistemic | None = None


class InsightFrontmatter(_Frontmatter):
    """A derived insight, wherever it lives (SYNTHESIS.md)."""

    origin: Literal["synthesis"]
    insight_kind: InsightKind
    status: InsightStatus
    derived_from: Annotated[StrList, Field(min_length=1)]
    epistemic: Epistemic | None = None


class MemoryRecordFrontmatter(_Frontmatter):
    """``memory/records/`` — durable personal knowledge (MEMORY.md)."""

    type: MemoryType
    provenance: Provenance
    status: MemoryStatus = "current"
    subject: str = "user"
    domains: StrList = Field(default_factory=list)
    observed_at: IsoDate | None = None
    valid_from: PartialDate | None = None
    valid_until: IsoDate | None = None
    superseded_by: str | None = None


class MemoryEventFrontmatter(_Frontmatter):
    """``memory/events/`` — append-oriented history (MEMORY.md)."""

    provenance: Provenance
    type: MemoryType | None = None
    status: MemoryStatus | None = None
    observed_at: IsoDate | None = None
    date: PartialDate | None = None


class MemoryStateFrontmatter(_Frontmatter):
    """``memory/state/`` — current-state projection (MEMORY.md)."""

    type: MemoryType | None = None
    provenance: Provenance | None = None
    status: MemoryStatus = "current"
    observed_at: IsoDate | None = None
    superseded_by: str | None = None


class WorkFrontmatter(_Frontmatter):
    """``projects/`` and ``areas/`` — action context (WORK.md)."""


# ------------------------------------------------------------------ dispatching

Layer = Literal[
    "source",
    "library",
    "wiki",
    "insight",
    "memory_record",
    "memory_event",
    "memory_state",
    "project",
    "area",
]

SCHEMAS: dict[str, type[_Frontmatter]] = {
    "source": SourceFrontmatter,
    "wiki": WikiFrontmatter,
    "insight": InsightFrontmatter,
    "memory_record": MemoryRecordFrontmatter,
    "memory_event": MemoryEventFrontmatter,
    "memory_state": MemoryStateFrontmatter,
    "project": WorkFrontmatter,
    "area": WorkFrontmatter,
}

# Directories that hold durable content. Everything else (inbox, logs, archive,
# indexes, scripts, docs, root files) is outside the validated layers.
CONTENT_ROOTS = ("library", "sources", "wiki", "memory", "projects", "areas")


def layer_for(rel_parts: tuple[str, ...], frontmatter: dict[str, Any]) -> Layer | None:
    """Decide which schema applies to a note at ``rel_parts`` (path parts).

    A note marked ``origin: synthesis`` is an insight wherever it lives, matching
    :func:`brain_core.records.classify`. Returns ``None`` outside content layers.
    """
    if not rel_parts or rel_parts[0] not in CONTENT_ROOTS:
        return None
    origin = frontmatter.get("origin")
    if isinstance(origin, str) and origin.strip().lower() == "synthesis":
        return "insight"
    top = rel_parts[0]
    if top == "sources":
        return "source"
    if top == "library":
        return "library"
    if top == "wiki":
        return "wiki"
    if top == "memory":
        sub = rel_parts[1] if len(rel_parts) > 2 else ""
        return {"records": "memory_record", "events": "memory_event", "state": "memory_state"}.get(
            sub, "memory_record"
        )
    return "project" if top == "projects" else "area"


def json_schema(layer: str) -> dict[str, Any]:
    """JSON Schema for a layer's frontmatter, for constrained LLM output."""
    return SCHEMAS[layer].model_json_schema()
