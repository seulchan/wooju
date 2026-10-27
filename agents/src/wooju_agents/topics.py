"""Write a new topic note from the notes that gathered around it.

The topics agent finds groups of close notes by computation (no AI). When the
user taps "make it a topic", this writes the note: a short name for the
subject and a few sentences on what the notes say together, each sentence
pointing at the notes it comes from (checked in code, like Ask). The user's
own words go elsewhere in the note; this is only the starting map.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Annotated

from pydantic import BaseModel, Field, ValidationError

from brain_core.messages import UserFacingError
from brain_core.records import Record

from .llm import Provider
from .text import normalize_korean

AGENT = "topics"
_LANGUAGE_NAME = {"ko": "Korean", "en": "English"}


class TopicError(UserFacingError):
    """The topic could not be written; ``key`` names the user message."""


class Sentence(BaseModel):
    text: str = Field(description="One sentence about what the notes say together.")
    sources: Annotated[list[int], Field(min_length=1)] = Field(
        description="Numbers of the notes this sentence comes from."
    )


class TopicDraft(BaseModel):
    title: str = Field(
        description="The subject these notes share, as a short name (2-6 words), not a claim."
    )
    summary: Annotated[list[Sentence], Field(min_length=1, max_length=5)]


_SYSTEM = (
    "You name the shared subject of a group of notes from someone's personal notebook "
    "and summarize what they say together. Use only the numbered notes. The title is "
    "the subject as a short name (2-6 words), the way a chapter or folder would be "
    "named, not a sentence and not a claim. The summary is 2-5 sentences on what the "
    "notes say about that subject, the most important first; give each sentence the "
    "numbers of the notes it comes from; if notes disagree, say so. Write in {language}."
)


@dataclass
class TopicNote:
    title: str
    body: str  # Markdown body: heading and summary, links to the members


def make_topic(members: list[Record], provider: Provider, *, language: str, path: str) -> TopicNote:
    """Title and summary for a topic note at ``path`` gathering ``members``."""
    listing = "\n\n".join(
        f"[{n}] {m.title}\n{' '.join(m.content.split())[:600]}" for n, m in enumerate(members, 1)
    )
    system = _SYSTEM.format(language=_LANGUAGE_NAME.get(language, "English"))
    result = provider.generate_json(system, f"Notes:\n\n{listing}", TopicDraft.model_json_schema())
    try:
        draft = TopicDraft.model_validate(result.data)
    except ValidationError as exc:
        raise TopicError(str(exc), "topic.bad_shape") from exc
    title = normalize_korean(" ".join(draft.title.split()).strip(" .\"'"))
    if not title:
        raise TopicError("No title", "topic.bad_shape")

    base = os.path.dirname(path)
    lines = []
    for s in draft.summary:
        text = s.text.strip()
        if not text:
            continue
        refs = []
        for n in dict.fromkeys(s.sources):
            if 1 <= n <= len(members):
                m = members[n - 1]
                rel = PurePosixPath(os.path.relpath(m.path, base)).as_posix()
                refs.append(f"[{m.title}]({rel})")
        text = normalize_korean(text) if language == "ko" else text
        lines.append(text + (f" ({', '.join(refs)})" if refs else ""))
    if not lines:
        raise TopicError("Empty summary", "topic.bad_shape")
    body = f"# {title}\n\n" + " ".join(re.sub(r"\s+", " ", x) for x in lines) + "\n"
    return TopicNote(title=title, body=body)
