"""Questions to think with: the AI asks, the user answers.

Research on learning (elaborative interrogation, self-explanation) and on AI
note-taking (notes the AI writes for you leave less understanding) point the
same way: the useful thing an AI can do here is ask. So this agent writes only
questions about one note: why it holds, how it connects to a specific other
note (found by search and checked in code), and where it would not hold.
It never writes an answer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import BaseModel, Field, ValidationError

from brain_core.records import Record

from .llm import Provider

Kind = Literal["why", "connect", "limits"]
_LANGUAGE_NAME = {"ko": "Korean", "en": "English"}


class QuestionItem(BaseModel):
    kind: Kind
    text: str = Field(description="One short, specific question about this note.")
    other: int = Field(
        default=0,
        description="For kind 'connect': the number of the other note it asks about; else 0.",
    )


class QuestionDraft(BaseModel):
    """The shape asked of the model (results are read leniently, item by item)."""

    questions: Annotated[list[QuestionItem], Field(min_length=1, max_length=3)]


_SYSTEM = (
    "You help someone think about a note in their personal notebook by asking them "
    "questions. Never answer, hint at an answer, or summarize. Ask up to three short, "
    "specific questions about this note, one of each kind where it makes sense: "
    "'why' (why does this hold, what explains it), 'connect' (how does this relate to one "
    "of the numbered other notes; set other to its number; only if a real link is "
    "plausible), and 'limits' (when would this not hold, what is a counterexample). "
    "Questions must be answerable from thinking, not from looking something up. "
    "Write them in {language}."
)


@dataclass
class Question:
    kind: str
    text: str
    related: Record | None = None


def make_questions(
    record: Record, others: list[Record], provider: Provider, *, language: str
) -> list[Question]:
    listing = "\n".join(
        f"[{n}] {o.title}: {' '.join(o.content.split())[:200]}" for n, o in enumerate(others, 1)
    )
    user = (
        f"The note:\n# {record.title}\n\n{record.content.strip()[:2500]}\n\n"
        f"Other notes:\n{listing or '(none)'}"
    )
    system = _SYSTEM.format(language=_LANGUAGE_NAME.get(language, "English"))
    result = provider.generate_json(system, user, QuestionDraft.model_json_schema())
    raw = result.data.get("questions") if isinstance(result.data, dict) else None
    items: list[QuestionItem] = []
    for entry in raw if isinstance(raw, list) else []:
        try:  # keep the good ones even if one is malformed
            items.append(QuestionItem.model_validate(entry))
        except ValidationError:
            continue
    out: list[Question] = []
    seen: set[str] = set()
    for item in items:
        if len(out) == 3:
            break
        text = item.text.strip()
        if not text or text in seen:
            continue
        related = None
        if item.kind == "connect":
            if not 1 <= item.other <= len(others):
                continue  # a connection must point at a note that exists
            related = others[item.other - 1]
        seen.add(text)
        out.append(Question(item.kind, text, related))
    return out
