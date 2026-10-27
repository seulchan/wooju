"""Topics: overview notes that gather the notes about one subject.

A topic is an overview note (``wiki/overviews/``). Its body is the user's (or
written once when the topic is created) and is never rewritten by an agent.
The topics agent owns exactly one section at the end, "Notes on this topic":
a list of links to member notes, which it only ever adds to.

``topic_notes`` in the frontmatter records what the agent added. When one of
those links has disappeared from the section, the user removed it on purpose:
it moves to ``topic_excluded`` and is never added again. That keeps the
user's hand on the skeleton of the Brain while the agent does the filing.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath

from .markdown import set_frontmatter_value, split_frontmatter
from .records import Record
from .vectors import cosine

TOPIC_FOLDER = "wiki/overviews"
SECTION = {"ko": "이 주제의 노트", "en": "Notes on this topic"}
ADDED_KEY = "topic_notes"
EXCLUDED_KEY = "topic_excluded"
_HEADINGS = "|".join(re.escape(h) for h in SECTION.values())
_SECTION_RE = re.compile(
    rf"^##[ \t]+(?:{_HEADINGS})[ \t]*$(?P<body>.*?)(?=^##[ \t]|\Z)", re.M | re.S
)
_LINK_RE = re.compile(r"\]\((?P<href>[^)\s]+\.md)\)")


def is_topic(record: Record) -> bool:
    return record.path.startswith(TOPIC_FOLDER + "/") and not record.retired


def _paths(value: object) -> list[str]:
    return [v for v in value if isinstance(v, str)] if isinstance(value, list) else []


@dataclass
class TopicState:
    added: list[str]  # Brain-relative paths the agent put in the section
    excluded: list[str]  # paths the user took out; never added again
    in_section: list[str]  # paths linked from the section right now


def read_state(text: str, topic_path: str) -> TopicState:
    frontmatter, body = split_frontmatter(text)
    in_section: list[str] = []
    m = _SECTION_RE.search(body)
    if m:
        base = os.path.dirname(topic_path)
        for link in _LINK_RE.finditer(m.group("body")):
            in_section.append(os.path.normpath(os.path.join(base, link.group("href"))))
    return TopicState(
        added=_paths(frontmatter.get(ADDED_KEY)),
        excluded=_paths(frontmatter.get(EXCLUDED_KEY)),
        in_section=[PurePosixPath(p).as_posix() for p in in_section],
    )


def _link(topic_path: str, member: Record) -> str:
    rel = os.path.relpath(member.path, os.path.dirname(topic_path))
    return f"- [{member.title}]({PurePosixPath(rel).as_posix()})"


def add_members(
    text: str, topic_path: str, members: list[Record], language: str
) -> tuple[str, list[str]]:
    """Add ``members`` to the topic's section; return the new text and what was added.

    Links the user removed since the agent added them are remembered as
    excluded first, so they are not put back. Members already linked anywhere
    in the note are skipped too: the user's own map comes first.
    """
    frontmatter, body = split_frontmatter(text)
    state = read_state(text, topic_path)
    removed = [p for p in state.added if p not in state.in_section]
    excluded = list(dict.fromkeys([*state.excluded, *removed]))
    added = [p for p in state.added if p not in removed]

    linked_anywhere = set(state.in_section)
    base = os.path.dirname(topic_path)
    for link in _LINK_RE.finditer(body):
        linked_anywhere.add(
            PurePosixPath(os.path.normpath(os.path.join(base, link.group("href")))).as_posix()
        )
    wiki_targets = {t.strip() for t in re.findall(r"\[\[([^\]|#^]+)", body)}

    new = [
        m
        for m in members
        if m.path != topic_path
        and m.path not in excluded
        and m.path not in linked_anywhere
        and m.id not in wiki_targets
        and m.id.split("/", 1)[-1] not in wiki_targets
    ]
    if not new and not removed:
        return text, []

    heading = SECTION.get(language, SECTION["en"])
    lines = [_link(topic_path, m) for m in new]
    m = _SECTION_RE.search(text)
    if m:
        existing = m.group("body").rstrip("\n")
        block = existing + ("\n" if existing.strip() else "\n\n") + "\n".join(lines) + "\n\n"
        updated = text[: m.start("body")] + block + text[m.end("body") :].lstrip("\n")
        updated = updated.rstrip("\n") + "\n"
    elif lines:
        updated = text.rstrip("\n") + f"\n\n## {heading}\n\n" + "\n".join(lines) + "\n"
    else:
        updated = text
    added += [m.path for m in new]
    updated = set_frontmatter_value(updated, ADDED_KEY, json.dumps(added, ensure_ascii=False))
    updated = set_frontmatter_value(
        updated, EXCLUDED_KEY, json.dumps(excluded, ensure_ascii=False) if excluded else None
    )
    return updated, [m.path for m in new]


def remove_member(text: str, topic_path: str, member_path: str) -> str:
    """Take one note out of the topic's section and remember not to add it again."""
    state = read_state(text, topic_path)
    rel = PurePosixPath(os.path.relpath(member_path, os.path.dirname(topic_path))).as_posix()
    updated = re.sub(rf"^- \[[^\]]*\]\({re.escape(rel)}\)[ \t]*\n?", "", text, flags=re.M)
    excluded = list(dict.fromkeys([*state.excluded, member_path]))
    added = [p for p in state.added if p != member_path]
    updated = set_frontmatter_value(updated, ADDED_KEY, json.dumps(added, ensure_ascii=False))
    return set_frontmatter_value(updated, EXCLUDED_KEY, json.dumps(excluded, ensure_ascii=False))


# ------------------------------------------------------------------ matching
#
# Calibrated with evals/topic_links.py against the links the user's own
# overviews already have (the gold set). Prefer missing a link to adding a
# wrong one: a missing link is visible and one tap away; wrong links quietly
# turn a topic into noise.
# On the dev Brain (3 topics, 19 links in the answer key): 0.75 → 80% precision,
# 47% recall; 0.78 → 88%, 41%. The "wrong" links left were ones the overview
# simply had not made yet (a 3rd-amendment source under the amendments topic).
LINK_MIN = 0.78  # a note joins a topic from here
LINK_MARGIN = 0.04  # ...and only topics this close to its best one
MAX_TOPICS_PER_NOTE = 2
CLUSTER_MIN = 0.72  # notes this close may form a new topic
CLUSTER_SIZE = 4  # at least this many notes before a new topic is suggested


def _mean(vectors: Sequence[Sequence[float]]) -> list[float]:
    total = [sum(col) for col in zip(*vectors, strict=True)]
    norm = sum(x * x for x in total) ** 0.5 or 1.0
    return [x / norm for x in total]


def topic_vector(
    topic_id: str, member_ids: Sequence[str], vectors: Mapping[str, Sequence[float]]
) -> list[float] | None:
    """A topic's place in meaning: its own note together with its members."""
    found = [vectors[i] for i in [topic_id, *member_ids] if i in vectors]
    return _mean(found) if found else None


def match_topics(
    note_vector: Sequence[float], topics: Mapping[str, Sequence[float]]
) -> list[tuple[float, str]]:
    """Topics a note belongs to: close enough, and close to its best match."""
    scored = sorted(((cosine(note_vector, v), tid) for tid, v in topics.items()), reverse=True)
    if not scored or scored[0][0] < LINK_MIN:
        return []
    best = scored[0][0]
    return [s for s in scored if s[0] >= LINK_MIN and best - s[0] <= LINK_MARGIN][
        :MAX_TOPICS_PER_NOTE
    ]


def emerging(vectors: Mapping[str, Sequence[float]], exclude: set[str]) -> list[list[str]]:
    """Groups of notes outside every topic that sit close together.

    Each group is a seed note and the notes close to it (at least CLUSTER_MIN),
    largest group first, a note in one group only. Deterministic for the
    same notes, so a suggestion the user dismissed stays recognisable.
    """
    ids = sorted(i for i in vectors if i not in exclude)
    near: dict[str, set[str]] = {i: set() for i in ids}
    for n, a in enumerate(ids):
        for b in ids[n + 1 :]:
            if cosine(vectors[a], vectors[b]) >= CLUSTER_MIN:
                near[a].add(b)
                near[b].add(a)
    groups: list[list[str]] = []
    taken: set[str] = set()
    for seed in sorted(ids, key=lambda i: (-len(near[i]), i)):
        if seed in taken:
            continue
        group = [seed, *sorted(near[seed] - taken)]
        if len(group) >= CLUSTER_SIZE:
            groups.append(group)
            taken.update(group)
    return groups
