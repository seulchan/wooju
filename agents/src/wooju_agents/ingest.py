"""Ingest agent: turn a file dropped into ``inbox/`` into a source-note proposal.

Routing is decided by origin, not by the model (phase 1 finding: small models
file external articles as personal memory). Anything dropped as a file is
external evidence, so it becomes:

* ``sources/<slug>.md``  — what the source says (written by the model, checked
  against the schema, then cleaned deterministically),
* ``library/<slug><ext>`` — the original file, kept for provenance,
* removal of the inbox file.

The model fills only what it can read from the text. Dates the app knows
(``accessed``) and references it can find (a URL in the text, or the library
copy) are set by code.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Annotated

import yaml
from pydantic import BaseModel, Field, ValidationError

from brain_core.changes import FileChange, Proposal, approval_for
from brain_core.messages import UserFacingError
from brain_core.schema import SourceFrontmatter, SourceType

from .capture import link_for
from .llm import Provider
from .text import ACCEPTED_SUFFIXES, UnsupportedFile, extract_text, first_url, normalize_korean

AGENT = "ingest"


class IngestError(UserFacingError):
    """A file cannot be turned into a source note; ``key`` names the user message."""


class SourceDraft(BaseModel):
    """What the model must return. Shape only; facts come from the text."""

    title: str = Field(description="The source's own title, in its original language.")
    source_type: SourceType
    authors: list[str] = Field(
        default_factory=list, description="Authors or publishing organization."
    )
    published: str = Field(
        default="unknown",
        description=(
            "Publication date as YYYY-MM-DD, YYYY-MM, or YYYY. "
            "'unknown' if the text does not state it."
        ),
    )
    one_line_summary: str = Field(
        description="One sentence: the main claim with its key number or date."
    )
    key_points: Annotated[list[str], Field(min_length=1, max_length=8)]
    limitations: list[str] = Field(
        default_factory=list,
        description="What the source does not show, or reasons to be careful with it.",
    )


_LANGUAGE_NAME = {"ko": "Korean", "en": "English"}

_SYSTEM = (
    "You write a source note for a personal knowledge base. Record only what the "
    "source text itself says. Do not add outside knowledge, guesses, or advice. "
    "If the text does not state the publication date, use 'unknown'. "
    "Write one_line_summary, key_points, and limitations in {language}. "
    "Keep the title exactly as the source writes it."
)

_HEADINGS = {
    "ko": ("한 줄 요약", "핵심 내용", "한계와 주의점", "원본", "원본 파일"),
    "en": ("One-line Summary", "Key Ideas", "Limitations / Caveats", "Original", "Original file"),
}


def inbox_files(brain: Path) -> list[str]:
    """Supported files waiting in ``inbox/``, oldest first."""
    inbox = brain / "inbox"
    if not inbox.is_dir():
        return []
    memos = inbox / "memos"
    files = [
        p
        for p in inbox.rglob("*")
        if p.is_file()
        and not p.name.startswith(".")
        and p.suffix.lower() in ACCEPTED_SUFFIXES
        and memos not in p.parents  # the user's own memos stay as written
    ]
    files.sort(key=lambda p: p.stat().st_mtime)
    return [p.relative_to(brain).as_posix() for p in files]


def slugify(text: str, max_len: int = 60) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    return slug[:max_len].rstrip("-")


def _unique(brain: Path, folder: str, stem: str, suffix: str) -> str:
    candidate = f"{folder}/{stem}{suffix}"
    n = 2
    while (brain / candidate).exists():
        candidate = f"{folder}/{stem}-{n}{suffix}"
        n += 1
    return candidate


def _clean_published(value: str) -> str:
    try:
        return (
            SourceFrontmatter.model_validate(
                {"source_type": "other", "canonical_ref": "x", "published": value}
            ).published
            or "unknown"
        )
    except ValidationError:
        return "unknown"


def build_note(
    draft: SourceDraft, *, canonical_ref: str, accessed: date, language: str, original_link: str
) -> str:
    fix = normalize_korean if language == "ko" else (lambda s: s)
    # "2026 년 10 월" is a model artifact, never how a Korean title is written.
    title = normalize_korean(draft.title.strip())
    frontmatter = {
        "title": title,
        "source_type": draft.source_type,
        "authors": [a.strip() for a in draft.authors if a.strip()],
        "published": _clean_published(draft.published),
        "accessed": accessed.isoformat(),
        "canonical_ref": canonical_ref,
        "status": "active",
    }
    SourceFrontmatter.model_validate(frontmatter)  # never emit a note the validator rejects
    h_summary, h_points, h_limits, h_original, original_label = _HEADINGS.get(
        language, _HEADINGS["en"]
    )
    lines = ["---", yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False).strip(), "---"]
    lines += [
        f"# {title}",
        "",
        f"## {h_summary}",
        "",
        fix(draft.one_line_summary.strip()),
        "",
    ]
    lines += (
        [f"## {h_points}", ""]
        + [f"- {fix(p.strip())}" for p in draft.key_points if p.strip()]
        + [""]
    )
    limits = [x.strip() for x in draft.limitations if x.strip()]
    if limits:
        lines += [f"## {h_limits}", ""] + [f"- {fix(x)}" for x in limits] + [""]
    lines += [f"## {h_original}", "", f"- [{original_label}]({original_link})", ""]
    return "\n".join(lines)


def ingest_file(
    brain: Path,
    rel: str,
    provider: Provider,
    *,
    language: str,
    today: date | None = None,
) -> Proposal:
    """Read ``rel`` (a path under ``inbox/``) and return a pending proposal."""
    rel_path = PurePosixPath(rel)
    if rel_path.parts[:1] != ("inbox",) or ".." in rel_path.parts:
        raise IngestError(f"Not an inbox path: {rel}", "ingest.inbox_only")
    path = brain / rel_path
    try:
        text, title_hint = extract_text(path)
    except UnsupportedFile as exc:
        raise IngestError(str(exc), "ingest.unsupported") from exc
    if len(text.strip()) < 40:
        raise IngestError("No text", "ingest.no_text")

    user = text if not title_hint else f"Title (from file metadata): {title_hint}\n\n{text}"
    system = _SYSTEM.format(language=_LANGUAGE_NAME.get(language, "English"))
    result = provider.generate_json(system, user, SourceDraft.model_json_schema())
    try:
        draft = SourceDraft.model_validate(result.data)
    except ValidationError as exc:
        raise IngestError(str(exc), "ingest.bad_shape") from exc

    draft.title = normalize_korean(draft.title.strip())
    stem = (
        slugify(draft.title)
        or slugify(path.stem)
        or f"source-{(today or date.today()).isoformat()}"
    )
    note_path = _unique(brain, "sources", stem, ".md")
    library_path = _unique(brain, "library", PurePosixPath(note_path).stem, path.suffix.lower())
    # A fetched link keeps its real address; otherwise the first URL in the text.
    canonical_ref = link_for(brain, rel) or first_url(text) or library_path
    note = build_note(
        draft,
        canonical_ref=canonical_ref,
        accessed=today or date.today(),
        language=language,
        original_link=f"../{library_path}",
    )
    changes = [
        FileChange(op="write", path=note_path, content=note),
        FileChange(op="copy", path=library_path, source=rel),
        FileChange(op="delete", path=rel),
    ]
    fix = normalize_korean if language == "ko" else (lambda s: s)
    title = (
        f"자료를 저장했어요: {draft.title}" if language == "ko" else f"Saved source: {draft.title}"
    )
    return Proposal(
        agent=AGENT,
        origin=rel,
        title=title,
        summary=fix(draft.one_line_summary.strip()),
        changes=changes,
        approval=approval_for(changes),
    )
