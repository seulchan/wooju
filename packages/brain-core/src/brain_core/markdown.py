"""Markdown parsing for Brain notes — pure functions, no filesystem access.

Handles YAML frontmatter, title extraction, search snippets, and Obsidian-style
wikilink extraction. Parsing is tolerant of malformed input: a bad frontmatter
block degrades to an empty dict rather than raising, so one broken note can never
sink the whole Brain. This module never writes anywhere (Invariant 4).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

BOM = "﻿"

# A level-1 heading anywhere in the body (used as a title fallback).
_H1_RE = re.compile(r"^#[ \t]+(.+?)[ \t]*$", re.MULTILINE)
# A level-2 heading — used as a title fallback only for daily-log notes whose
# sole H1 is a date banner (see :func:`extract_title`).
_H2_RE = re.compile(r"^##[ \t]+(.+?)[ \t]*$", re.MULTILINE)
# A bare ISO date, e.g. "2026-08-08". A heading that is only a date is a
# daily-note/journal date banner, not a record's intended title.
_DATE_ONLY_RE = re.compile(r"^\d{4}-\d{1,2}-\d{1,2}$")

# Wikilink form: [[target#anchor^block|Label]]
# Negative lookbehind for '!' skips image/file embeds (![[...]]).
# Target excludes ], [, |, #, ^. An optional #/^ separator + anchor, then an
# optional |Label, all inside [[ ... ]].
_WIKILINK_RE = re.compile(
    r"(?<!\!)\[\["
    r"(?P<target>[^\]\[|^#]+)"  # note path
    r"(?:[#^](?P<anchor>[^\]\[|]*))?"  # heading (#) or block (^) reference
    r"(?:\|(?P<label>[^\]\[]*))?"  # optional custom label
    r"\]\]"
)


def normalize_text(text: str) -> str:
    """Strip a UTF-8 BOM and normalize CRLF/CR to LF.

    BOM and Windows line endings break naive ``startswith("---\\n")`` checks and
    heading/wikilink regexes, so every parse normalizes first.
    """
    if text.startswith(BOM):
        text = text[len(BOM) :]
    return text.replace("\r\n", "\n").replace("\r", "\n")


def split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Split a note into ``(frontmatter, body)``.

    Frontmatter is a leading ``---``-delimited YAML block. Returns ``({}, body)``
    when there is no frontmatter, when the block is empty/non-mapping, or when the
    YAML fails to parse — never raises. ``body`` has the frontmatter stripped.
    """
    normalized = normalize_text(text)
    lines = normalized.split("\n")

    # A frontmatter block must start on the very first line with "---".
    if not lines or lines[0].strip() != "---":
        return {}, normalized

    close_idx: int | None = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            close_idx = i
            break
    if close_idx is None:
        # Opening "---" with no closing delimiter is not frontmatter.
        return {}, normalized

    raw_yaml = "\n".join(lines[1:close_idx])
    body = "\n".join(lines[close_idx + 1 :])

    if not raw_yaml.strip():
        return {}, body

    try:
        data = yaml.safe_load(raw_yaml)
    except yaml.YAMLError:
        return {}, body

    if not isinstance(data, dict):
        # A bare scalar/list or empty block is not useful frontmatter.
        return {}, body
    return data, body


def extract_title(frontmatter: dict[str, Any], body: str, filename: str) -> str:
    """Derive a note title.

    Preference: a non-empty, non-date frontmatter ``title`` → the first non-date
    H1 in the body → (for daily-log notes whose only H1 is a date banner) the
    first non-date H2 → the filename stem. Always returns a non-empty string.

    A heading or metadata title whose text is a bare date (e.g. ``# 2026-08-08``)
    is a daily-note date banner, not a title: it is skipped. When that date banner
    was the only H1 — the Brain's ``logs/`` journal convention (``# DATE`` then
    ``## entry``) — the entry's H2 is the meaningful title. Normal notes keep
    their existing H1-then-filename behavior unchanged.
    """
    raw_title = frontmatter.get("title")
    if isinstance(raw_title, str) and raw_title.strip() and not _is_date_only(raw_title):
        return raw_title.strip()

    # First non-date H1. Track whether any H1 was a date banner so a daily-log
    # note (whose only H1 is a date) can fall through to its entry H2 below.
    saw_date_banner = False
    for match in _H1_RE.finditer(body):
        h1 = match.group(1).strip()
        if _is_date_only(h1):
            saw_date_banner = True
            continue
        return h1

    if saw_date_banner:
        for h2_match in _H2_RE.finditer(body):
            h2 = h2_match.group(1).strip()
            if not _is_date_only(h2):
                return h2

    return Path(filename).stem


def _is_date_only(value: str) -> bool:
    """Return whether ``value`` is a bare ISO-like calendar date."""
    return bool(_DATE_ONLY_RE.fullmatch(value.strip()))


def extract_wikilinks(body: str) -> list[dict[str, Any]]:
    """Extract Obsidian-style wikilinks from ``body``.

    Each result is ``{"target", "label", "anchor"}`` — all pre-resolution.
    Embeds (``![[...]]``) are ignored. Empty targets are skipped.
    """
    links: list[dict[str, Any]] = []
    for match in _WIKILINK_RE.finditer(body):
        target = match.group("target").strip()
        if not target:
            continue
        label = match.group("label")
        anchor = match.group("anchor")
        links.append(
            {
                "target": target,
                "label": label.strip() if label else None,
                "anchor": anchor.strip() if anchor else None,
            }
        )
    return links


# A self-contained ``[[target]]`` reference (optional #/^ anchor, |label).
_REF_WIKILINK_RE = re.compile(r"^\[\[(?P<inner>[^\]\[|^#]+)(?:[#^][^\]\[|]*)?(?:\|[^\]\[]*)?\]\]$")
# A Markdown ``[label](href)`` reference.
_REF_MD_LINK_RE = re.compile(r"^\[(?P<label>[^\]]*)\]\((?P<href>[^)]+)\)$")


def normalize_target(ref: Any) -> str | None:
    """Reduce a derivation/wikilink reference to its canonical record target.

    The Brain writes ``derived_from`` in several forms:

    - ``[[overviews/foo]]``                 → ``overviews/foo``
    - ``[[concepts/foo|Label]]`` / anchors  → ``concepts/foo``
    - ``[Label](../../sources/foo.md)``     → ``sources/foo``
    - a bare path/id ``wiki/foo`` / ``foo`` → unchanged

    Anchors (``#``/``^``), labels, the ``.md`` suffix, and leading ``./`` /
    ``../`` traversal segments are stripped so the result can be matched against
    record ids. Returns ``None`` for empty/unparseable input. Pure — it never
    touches the filesystem.
    """
    if not isinstance(ref, str):
        return None
    s = ref.strip()
    if not s:
        return None

    m = _REF_WIKILINK_RE.match(s)
    if m:
        s = m.group("inner").strip()
    else:
        m = _REF_MD_LINK_RE.match(s)
        if m:
            s = m.group("href").strip()

    # Drop any residual fragment/query so an anchor never reaches resolution.
    s = s.split("#", 1)[0].split("?", 1)[0].strip()
    if not s:
        return None
    if s.endswith(".md"):
        s = s[:-3]
    # Strip leading "./" and "../" segments from nested-note relative paths.
    while s.startswith("../") or s.startswith("./"):
        s = s.split("/", 1)[1] if "/" in s else ""
    return s or None


def make_snippet(content: str, terms: list[str], width: int = 200) -> str:
    """Build a short text snippet around the first matched term.

    Used for search hit previews. Falls back to the start of the body when no
    term is found. Returns plain, single-line text.
    """
    if not content.strip():
        return ""
    lowered = content.lower()
    idx = -1
    for term in terms:
        pos = lowered.find(term)
        if pos != -1:
            idx = pos
            break
    if idx == -1:
        idx = 0
    start = max(0, idx - width // 2)
    end = min(len(content), idx + width // 2)
    snippet = content[start:end].replace("\n", " ").strip()
    if start > 0 or end < len(content):
        snippet = f"…{snippet}…"
    return snippet


def set_frontmatter_value(text: str, key: str, value: str | None) -> str:
    """Set, add, or (``value=None``) remove one top-level scalar frontmatter key.

    Edits only that line, so the rest of the file — comments, key order, quoting —
    stays exactly as the user wrote it. A file without frontmatter gets one.
    """
    import re

    line = f"{key}: {value}" if value is not None else None
    if not text.startswith("---"):
        return f"---\n{line}\n---\n{text}" if line else text
    lines = text.split("\n")
    close = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if close is None:
        raise ValueError("Frontmatter never closes")
    pattern = re.compile(rf"^{re.escape(key)}\s*:")
    for i in range(1, close):
        if pattern.match(lines[i]):
            if line is None:
                del lines[i]
            else:
                lines[i] = line
            return "\n".join(lines)
    if line is not None:
        lines.insert(close, line)
    return "\n".join(lines)
