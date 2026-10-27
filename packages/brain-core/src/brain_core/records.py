"""Normalized domain model for a Brain note, plus classification logic.

A ``Record`` is the in-memory, read-only representation of one Markdown note.
Classification (category/subtype/kind/status) reads existing Brain metadata and
structure only — it invents no taxonomy. This module never writes to the Brain
(Invariant 4): records are derived views, the filesystem stays canonical.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

Category = Literal["knowledge", "insight", "source", "memory", "project", "area", "other"]

# Top-level directory → category. "library/" holds original artifacts alongside
# "sources/" source notes; both surface as the "source" category.
_DIR_CATEGORY: dict[str, Category] = {
    "wiki": "knowledge",
    "sources": "source",
    "library": "source",
    "memory": "memory",
    "projects": "project",
    "areas": "area",
}

# Metadata values (case-insensitive) that mark a note as a derived insight,
# regardless of where it lives in the Brain. Derived insights override location.
_INSIGHT_ORIGINS = {"synthesis"}
_INSIGHT_TYPES = {"insight", "synthesis"}


class Link(BaseModel):
    """A wikilink found in a note's body, before/after resolution."""

    target: str  # raw target as written, e.g. "concepts/x" or "x"
    label: str | None = None
    anchor: str | None = None
    resolved_id: str | None = None  # id of the resolved record, or None if unresolved


class ResolvedRef(BaseModel):
    """A derivation reference (e.g. from ``derived_from``), before/after resolution.

    ``derived_from`` is derivation provenance — not proof. The field name is
    intentionally preserved (never renamed to "evidence"). ``ref`` is the value
    exactly as written (may be ``[[wikilink]]`` or ``[label](path)`` form);
    ``resolved_id``/``title`` are the best-effort target record, when one exists.
    """

    ref: str  # original reference as written
    resolved_id: str | None = None
    title: str | None = None  # title of the resolved record, for readable links


class Record(BaseModel):
    """One normalized note. All fields are derived, read-only views of the file."""

    id: str  # relative path without extension, e.g. "wiki/concepts/llm-agent-memory"
    path: str  # relative path with extension
    title: str
    # The frontmatter title when the note's heading differs (e.g. a source's
    # original-language title); ``title`` is then the heading shown to people.
    original_title: str | None = None
    category: Category
    subtype: str | None = None
    content: str  # markdown body, frontmatter stripped
    metadata: dict[str, Any] = Field(default_factory=dict)  # raw frontmatter
    links: list[Link] = Field(default_factory=list)
    modified_at: str | None = None  # ISO-8601 UTC of file mtime
    status: str | None = None  # insight status: candidate/provisional/established/...
    kind: str | None = None  # insight kind
    derived_from: list[str] = Field(default_factory=list)  # raw derivation refs
    derived_from_resolved: list[ResolvedRef] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)  # for search/display


def coerce_list(value: Any) -> list[str]:
    """Coerce a frontmatter value into a list of strings.

    Accepts ``None``→[], a scalar string→[string], a list of strings, or a list
    of mappings (best-effort: pull ``name``/``id``/``path``/``title``/``ref``).
    Non-string scalars are stringified. Used for ``aliases`` and ``derived_from``.
    """
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (int, float)):
        return [str(value)]
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, (int, float)):
            out.append(str(item))
        elif isinstance(item, dict):
            for key in ("name", "id", "path", "title", "ref"):
                val = item.get(key)
                if isinstance(val, str) and val.strip():
                    out.append(val.strip())
                    break
    return out


def _scalar(frontmatter: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    """First non-empty string value among ``keys`` in ``frontmatter``."""
    for key in keys:
        val = frontmatter.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


def _as_lower_str(value: Any) -> str:
    if isinstance(value, str):
        return value.strip().lower()
    return ""


def classify(
    rel_path: Path, frontmatter: dict[str, Any]
) -> tuple[Category, str | None, str | None, str | None]:
    """Classify a note into ``(category, subtype, kind, status)``.

    Category precedence is **metadata-wins and exclusive**: a note whose
    ``origin``/``type`` marks it as a derived synthesis is an ``insight`` even if
    it lives under ``wiki/`` (and is therefore excluded from knowledge listings).
    Otherwise the top-level directory decides. Unknown directories → ``other``.

    ``subtype`` reads ``subtype`` → ``type`` (wiki/knowledge convention) →
    ``source_type`` (the Brain's source-note convention, e.g. ``paper``). ``kind``
    reads ``insight_kind`` (the Brain's convention: ``pattern``/``tension``/…)
    then a generic ``kind``.

    Status is the **insight lifecycle** (``candidate``/``provisional``/
    ``established``…) and is read verbatim only for insights — per
    ``docs/EPISTEMICS.md`` the top-level ``status`` is the insight page's
    lifecycle. A source's ``status: active`` (availability) is a different
    semantic, so it is *not* promoted to the epistemic status (it remains in raw
    ``metadata``). A missing status stays ``None`` and **established is never
    inferred**.
    """
    origin = _as_lower_str(frontmatter.get("origin"))
    ftype = _as_lower_str(frontmatter.get("type"))

    if origin in _INSIGHT_ORIGINS or ftype in _INSIGHT_TYPES:
        category: Category = "insight"
    elif rel_path.parts[:2] == ("inbox", "memos"):
        # The user's own captured memos: personal, kept as written.
        category = "memory"
    else:
        top = rel_path.parts[0] if rel_path.parts else ""
        category = _DIR_CATEGORY.get(top, "other")

    subtype = _scalar(frontmatter, ("subtype", "type", "source_type"))
    kind = _scalar(frontmatter, ("insight_kind", "kind"))
    status = _scalar(frontmatter, ("status",)) if category == "insight" else None
    return category, subtype, kind, status
