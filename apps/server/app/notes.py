"""Notes the user writes in the app: new notes and one-line takeaways.

Wooju's agents organize what others wrote; this is where the user writes their
own. Only the form is provided (folder, frontmatter, a few headings in the
Brain's language); every word under them is the user's. A "thought" is an
insight in the Brain's terms (SYNTHESIS.md): a derived idea, so it must name
the notes it rests on and starts as a candidate.
"""

from __future__ import annotations

import os
import re
from datetime import date, datetime
from pathlib import Path, PurePosixPath
from typing import Literal

import yaml

from brain_core.records import Record
from wooju_agents.ingest import slugify

NoteKind = Literal["concept", "overview", "question", "how-to", "mental-model", "thought"]
InsightKind = Literal["hypothesis", "connection", "pattern", "implication", "tension"]

FOLDERS: dict[str, str] = {
    "concept": "wiki/concepts",
    "overview": "wiki/overviews",
    "question": "wiki/questions",
    "how-to": "wiki/how-tos",
    "mental-model": "wiki/mental-models",
    "thought": "wiki/questions",  # where this Brain keeps derived ideas under review
}

HEADINGS: dict[str, dict[str, list[str]]] = {
    "ko": {
        "concept": ["무엇인가", "왜 중요한가", "예시", "관련"],
        "overview": ["요약", "핵심", "관련"],
        "question": ["질문", "지금까지 아는 것", "아직 모르는 것", "현재 답"],
        "how-to": ["언제 쓰나", "순서", "주의할 점"],
        "mental-model": ["무엇인가", "언제 쓰나", "한계"],
    },
    "en": {
        "concept": ["What it is", "Why it matters", "Example", "Related"],
        "overview": ["Summary", "Key points", "Related"],
        "question": ["Question", "What we know", "What we don't know", "Current answer"],
        "how-to": ["When to use it", "Steps", "Watch out for"],
        "mental-model": ["What it is", "When to use it", "Limits"],
    },
}

# Insight sections are structural (the validator looks for them): English.
_WHY = {"ko": "왜 중요한가", "en": "Why it may matter"}
TAKEAWAY = {"ko": "내 생각", "en": "My Takeaway"}


def skeleton(kind: str, language: str) -> str:
    """The headings a new note starts with (the app shows them in the editor)."""
    if kind == "thought":
        return f"## Insight\n\n\n\n## {_WHY.get(language, _WHY['en'])}\n\n"
    heads = HEADINGS.get(language, HEADINGS["en"]).get(kind, [])
    return "".join(f"## {h}\n\n\n\n" for h in heads)


def note_path(brain: Path, kind: str, title: str, now: datetime | None = None) -> str:
    folder = FOLDERS[kind]
    stem = slugify(title)
    if len(stem) < 3:  # e.g. a Korean title: name the file by kind and time
        stem = f"{kind}-{(now or datetime.now()).strftime('%Y%m%d-%H%M%S')}"
    candidate, n = f"{folder}/{stem}.md", 2
    while (brain / candidate).exists():
        candidate, n = f"{folder}/{stem}-{n}.md", n + 1
    return candidate


def _link(from_path: str, target: Record) -> str:
    rel = os.path.relpath(target.path, os.path.dirname(from_path))
    return f"[{target.title}]({PurePosixPath(rel).as_posix()})"


def build(
    *,
    path: str,
    kind: str,
    title: str,
    body: str,
    grounds: list[Record],
    insight_kind: str = "hypothesis",
    review_after: date | None = None,
) -> str:
    frontmatter: dict[str, object] = {"title": title.strip()}
    if review_after:
        # First recall a week after writing it (see "recall" below).
        frontmatter["review_after"] = review_after
        frontmatter["review_interval"] = FIRST_REVIEW_DAYS
    if kind == "thought":
        frontmatter.update(
            origin="synthesis",
            insight_kind=insight_kind,
            status="candidate",
            derived_from=[_link(path, g) for g in grounds],
        )
    head = yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False).strip()
    text = body.replace("\r\n", "\n").strip()
    if not re.match(r"^#\s", text):
        text = f"# {title.strip()}\n\n{text}"
    return f"---\n{head}\n---\n{text}\n"


def set_takeaway(note: str, text: str, language: str) -> str:
    """Put the user's one line into the note's own section (replacing an earlier one)."""
    heading = TAKEAWAY.get(language, TAKEAWAY["en"])
    names = "|".join(re.escape(h) for h in TAKEAWAY.values())
    block = f"## {heading}\n\n{text.strip()}\n"
    existing = re.search(rf"^##\s+({names})\s*$.*?(?=^##\s|\Z)", note, re.M | re.S)
    if existing:
        return note[: existing.start()] + block + "\n" + note[existing.end() :].lstrip("\n")
    # Right after the source's summary and key ideas: before conflicts and links.
    anchor = re.search(r"^##\s+(Conflicts|원본|Original)\s*$", note, re.M)
    if anchor:
        return note[: anchor.start()] + block + "\n" + note[anchor.start() :]
    return note.rstrip("\n") + "\n\n" + block


def takeaway_of(content: str) -> str | None:
    names = "|".join(re.escape(h) for h in TAKEAWAY.values())
    m = re.search(rf"^##\s+({names})\s*$(.*?)(?=^##\s|\Z)", content, re.M | re.S)
    return m.group(2).strip() if m and m.group(2).strip() else None


# ------------------------------------------------------------------ recall

Rating = Literal["good", "partial", "poor"]
FIRST_REVIEW_DAYS = 7
DEFAULT_INTERVAL = 30
MAX_INTERVAL = 365


def next_interval(previous: int | None, rating: str) -> int:
    """Days until the next recall: spaced further apart as the note sticks."""
    prev = previous or DEFAULT_INTERVAL
    if rating == "good":
        return min(MAX_INTERVAL, max(DEFAULT_INTERVAL, prev * 2))
    if rating == "partial":
        return max(14, prev)
    return FIRST_REVIEW_DAYS


def _recall_log() -> Path:
    from brain_core.changes import data_dir

    return data_dir() / "recall.json"


def log_recall(brain: Path, record_id: str, rating: str, today: datetime | None = None) -> None:
    """Keep a small local log so the app can show how recall is going."""
    import json

    path = _recall_log()
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        entries = []
    entries.append(
        {
            "brain": str(brain),
            "id": record_id,
            "rating": rating,
            "at": (today or datetime.now()).isoformat(timespec="seconds"),
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries[-2000:], ensure_ascii=False), encoding="utf-8")


def recall_stats(brain: Path, days: int = 30, today: datetime | None = None) -> dict[str, object]:
    import json
    from datetime import timedelta

    try:
        entries = json.loads(_recall_log().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        entries = []
    since = (today or datetime.now()) - timedelta(days=days)
    recent = [
        e
        for e in entries
        if e.get("brain") == str(brain) and datetime.fromisoformat(e["at"]) >= since
    ]
    good = sum(1 for e in recent if e.get("rating") == "good")
    return {"count": len(recent), "good": good, "days": days}
