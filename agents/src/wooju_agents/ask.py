"""Ask agent: answer a question from the user's own Brain, with sources.

The model sees only numbered passages retrieved from the Brain and must cite
them as [1], [2]. Citations are checked in code: a number that does not point
to a passage is removed, and the remaining ones are renumbered in reading
order. If nothing relevant is found, no model is called and the answer says so.
Ask never writes to the Brain.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Annotated, Any

from pydantic import BaseModel, Field, ValidationError

from brain_core.index import BrainIndex
from brain_core.messages import UserFacingError
from brain_core.retrieve import Passage, Retriever

from .llm import Provider

MAX_PASSAGES = 8
# Below this BM25 score, or with fewer hits, the question is retried with
# model-written search terms (other language, synonyms, names).
WEAK_SCORE = 6.0
WEAK_HITS = 3
_LANGUAGE_NAME = {"ko": "Korean", "en": "English"}


class AskError(UserFacingError):
    """The question cannot be answered; ``key`` names the user message."""


class SearchTerms(BaseModel):
    queries: Annotated[list[str], Field(min_length=1, max_length=4)] = Field(
        description="Short keyword searches, each 1-4 words."
    )


class Statement(BaseModel):
    text: str = Field(description="One sentence of the answer.")
    sources: Annotated[list[int], Field(min_length=1)] = Field(
        description="Numbers of the passages this sentence comes from."
    )


class AnswerDraft(BaseModel):
    # Small local models skip inline [n] markers when asked for prose, so each
    # sentence carries its passage numbers as a required field instead.
    statements: list[Statement] = Field(
        description="The answer as sentences: the direct answer first, then supporting points."
    )
    enough: bool = Field(description="False if the passages do not answer the question.")


_TERMS_SYSTEM = (
    "You help search a personal investment-research notebook written mostly in Korean "
    "and English. Given a question, write up to 4 short keyword searches that would match "
    "notes answering it: include Korean and English forms, synonyms, tickers, and company "
    "or person names. Keywords only, no full sentences."
)

_ANSWER_SYSTEM = (
    "You answer questions using only the numbered passages from the user's own notes. "
    "Rules: use no outside knowledge; give each sentence the numbers of the passages it "
    "comes from; if passages disagree, say so; if they do not answer the question, say "
    "plainly what is missing and set enough to false; give no investment advice or price "
    "predictions of your own. Write every sentence in {language}, concisely: the direct "
    "answer first, then at most four supporting points."
)
_HANGUL = re.compile(r"[가-힣]")


def answer_language(question: str, default: str) -> str:
    """Answer in the question's language: Korean if it contains Hangul, else the app's."""
    if _HANGUL.search(question):
        return "ko"
    return "en" if re.search(r"[A-Za-z]", question) else default


@dataclass
class Citation:
    n: int
    id: str
    title: str
    heading: str | None
    category: str
    excerpt: str


@dataclass
class Answer:
    question: str
    answer: str
    found: bool
    citations: list[Citation] = field(default_factory=list)
    # True when the citations are notes the AI read but did not cite.
    related_only: bool = False
    model: str | None = None
    seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _excerpt(text: str, limit: int = 220) -> str:
    flat = " ".join(line.strip("-* ").strip() for line in text.splitlines() if line.strip())
    return flat if len(flat) <= limit else flat[: limit - 1].rstrip() + "…"


def gather(
    retriever: Retriever, question: str, provider: Provider | None
) -> tuple[list[Passage], float]:
    """Passages for ``question``; widens the search with the model when results are weak."""
    hits = retriever.search(question, limit=MAX_PASSAGES)
    seconds = 0.0
    if provider is not None and (len(hits) < WEAK_HITS or hits[0][0] < WEAK_SCORE):
        result = provider.generate_json(_TERMS_SYSTEM, question, SearchTerms.model_json_schema())
        seconds += result.seconds
        try:
            extra = SearchTerms.model_validate(result.data).queries
        except ValidationError:
            extra = []
        # Merge by best score per passage across the original and extra searches.
        best: dict[tuple[str, str | None, str], tuple[float, Passage]] = {}
        for query in [question, *extra]:
            for score, p in retriever.search(query, limit=MAX_PASSAGES):
                key = (p.id, p.heading, p.text[:50])
                if key not in best or best[key][0] < score:
                    best[key] = (score, p)
        hits = sorted(best.values(), key=lambda sp: (-sp[0], sp[1].record.path))
        per_note: dict[str, int] = {}
        kept = []
        for score, p in hits:
            if per_note.get(p.id, 0) < 2:
                per_note[p.id] = per_note.get(p.id, 0) + 1
                kept.append((score, p))
        hits = kept[:MAX_PASSAGES]
    return [p for _, p in hits], seconds


def _prompt(question: str, found: list[Passage]) -> str:
    blocks = []
    for n, p in enumerate(found, 1):
        where = p.record.title + (f" — {p.heading}" if p.heading else "")
        kind = p.record.category
        date = p.record.metadata.get("published") or p.record.metadata.get("observed_at")
        meta = f"{kind}" + (f", {date}" if date else "")
        blocks.append(f"[{n}] {where} ({meta})\n{p.text.strip()}")
    return "Passages:\n\n" + "\n\n".join(blocks) + f"\n\nQuestion: {question}"


def _cite(text: str, found: list[Passage]) -> tuple[str, list[Citation]]:
    """Keep only citations that point to a passage, renumbered in reading order."""
    order: dict[int, int] = {}

    def renumber(m: re.Match[str]) -> str:
        nums = [int(x) for x in re.findall(r"\d+", m.group(0))]
        out = []
        for n in nums:
            if 1 <= n <= len(found):
                order.setdefault(n, len(order) + 1)
                out.append(f"[{order[n]}]")
        return "".join(dict.fromkeys(out))

    cleaned = re.sub(r"\[\s*\d+(?:\s*[,，]\s*\d+)*\s*\]", renumber, text)
    cleaned = re.sub(r"[ \t]+([.,。])", r"\1", cleaned).strip()
    citations = []
    for original, n in sorted(order.items(), key=lambda kv: kv[1]):
        p = found[original - 1]
        citations.append(
            Citation(n, p.id, p.record.title, p.heading, p.record.category, _excerpt(p.text))
        )
    return cleaned, citations


def ask(
    index: BrainIndex,
    question: str,
    provider: Provider,
    *,
    language: str,
    retriever: Retriever | None = None,
) -> Answer:
    question = question.strip()
    if not question:
        raise AskError("Empty question", "ask.empty")
    if len(question) > 1000:
        raise AskError("Question too long", "ask.too_long")
    retriever = retriever or Retriever(index)
    found, seconds = gather(retriever, question, provider)
    if not found:
        return Answer(question, "", found=False, seconds=seconds)

    language = answer_language(question, language)
    system = _ANSWER_SYSTEM.format(language=_LANGUAGE_NAME.get(language, "English"))
    result = provider.generate_json(
        system, _prompt(question, found), AnswerDraft.model_json_schema()
    )
    try:
        draft = AnswerDraft.model_validate(result.data)
    except ValidationError as exc:
        raise AskError(str(exc), "ask.bad_shape") from exc
    lines = []
    for i, s in enumerate(draft.statements):
        marks = "".join(f"[{n}]" for n in dict.fromkeys(s.sources))
        text = s.text.strip().rstrip()
        if not text:
            continue
        lines.append(f"{'' if i == 0 else '- '}{text} {marks}".rstrip())
    text, citations = _cite("\n".join(lines), found)
    if not citations:
        # The model cited nothing usable: show what it read, so the user can check.
        citations = [
            Citation(n, p.id, p.record.title, p.heading, p.record.category, _excerpt(p.text))
            for n, p in enumerate(found[:3], 1)
        ]
        return Answer(
            question,
            re.sub(r"\s*\[\d+\]", "", text),
            found=False,
            citations=citations,
            related_only=True,
            model=result.model,
            seconds=seconds + result.seconds,
        )
    return Answer(
        question,
        text,
        found=draft.enough,
        citations=citations,
        model=result.model,
        seconds=seconds + result.seconds,
    )
