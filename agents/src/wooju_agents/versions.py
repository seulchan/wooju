"""A saved source that came in again with different text: a new version.

A link saved before is fetched again when it is sent again. If its text is
the same (allowing the small changes a web page makes on every visit), it is
a duplicate as before. If it really changed, the new text becomes a new
source note, and the earlier note is retired with ``superseded_by`` pointing
at it — so notes that rest on the earlier one are flagged "grounds changed",
and Ask no longer uses the earlier version. The new note says what changed:
the sentences added and removed, found by code (not by the AI).
"""

from __future__ import annotations

import difflib
import json
from dataclasses import dataclass
from datetime import date

from brain_core.markdown import set_frontmatter_value, split_frontmatter

from . import evidence

# Below this, a change is page noise (a date, a view count, a menu item).
MIN_CHANGED_PASSAGES = 2
MIN_CHANGED_CHARS = 160
SHOWN = 5

_HEADING = {"ko": "이전 버전과 달라진 점", "en": "What changed since the earlier version"}
_LINES = {
    "ko": ("이전 버전: [{title}]({link})", "새로 들어간 문장", "빠진 문장", "외 {n}개"),
    "en": ("Earlier version: [{title}]({link})", "Added", "Removed", "and {n} more"),
}
_REASON = {
    "ko": "새 버전이 들어왔어요: {path}",
    "en": "A newer version came in: {path}",
}


@dataclass
class Changes:
    added: list[str]
    removed: list[str]

    @property
    def significant(self) -> bool:
        changed = self.added + self.removed
        return len(changed) >= MIN_CHANGED_PASSAGES and sum(map(len, changed)) >= MIN_CHANGED_CHARS


def compare(old_text: str, new_text: str) -> Changes:
    """Sentences (passages) added and removed between two texts, in order."""
    old, new = evidence.passages(old_text), evidence.passages(new_text)
    added: list[str] = []
    removed: list[str] = []
    matcher = difflib.SequenceMatcher(a=old, b=new, autojunk=False)
    for op, a1, a2, b1, b2 in matcher.get_opcodes():
        if op in ("replace", "delete"):
            removed += old[a1:a2]
        if op in ("replace", "insert"):
            added += new[b1:b2]
    return Changes(added, removed)


def _quote_line(text: str) -> str:
    line = " ".join(text.split()).replace("[", "\\[")
    return line if len(line) <= 300 else line[:299].rstrip() + "…"


def section(changes: Changes, *, earlier_title: str, earlier_link: str, language: str) -> str:
    """The "what changed" section for the new note."""
    earlier, added, removed, more = _LINES.get(language, _LINES["en"])
    lines = [f"## {_HEADING.get(language, _HEADING['en'])}", ""]
    lines.append(f"- {earlier.format(title=earlier_title, link=earlier_link)}")
    for label, items in ((added, changes.added), (removed, changes.removed)):
        if not items:
            continue
        lines.append(f"- {label}:")
        lines += [f"  > {_quote_line(x)}" for x in items[:SHOWN]]
        if len(items) > SHOWN:
            lines.append(f"  - {more.format(n=len(items) - SHOWN)}")
    return "\n".join(lines) + "\n"


def add_section(note: str, block: str) -> str:
    """Put ``block`` just before the note's last section (the link to the original)."""
    at = note.rfind("\n## ")
    if at < 0:
        return note.rstrip() + "\n\n" + block
    return note[: at + 1] + block + "\n" + note[at + 1 :]


def retire_earlier(text: str, *, new_path: str, today: date, language: str) -> str:
    """The earlier note, retired in favour of ``new_path`` (as the Retire action does)."""
    before = split_frontmatter(text)[0].get("status")
    out = set_frontmatter_value(text, "retired", today.isoformat())
    out = set_frontmatter_value(out, "superseded_by", new_path)
    reason = _REASON.get(language, _REASON["en"]).format(path=new_path)
    out = set_frontmatter_value(out, "retired_reason", json.dumps(reason, ensure_ascii=False))
    if before and before != "archived":
        out = set_frontmatter_value(out, "status_before_retired", str(before))
    return set_frontmatter_value(out, "status", "archived")
