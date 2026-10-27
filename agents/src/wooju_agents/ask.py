"""Ask agent: answer a question from the user's own Brain, with sources.

The model sees only numbered passages retrieved from the Brain and must cite
them as [1], [2]. Citations are checked in code: a number that does not point
to a passage is removed, and the remaining ones are renumbered in reading
order. If nothing relevant is found, no model is called and the answer says so.
Ask never writes to the Brain.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from typing import Annotated, Any

from pydantic import BaseModel, Field, ValidationError

from brain_core.index import BrainIndex
from brain_core.messages import UserFacingError
from brain_core.records import Record
from brain_core.retrieve import Passage, Retriever

from .conflicts import first_conflict
from .llm import Provider

# Measured on an M1 with qwen3.5:9b (evals/ask_quality.py): reading time grows
# with the passages sent, so send fewer, shorter ones. Override per call.
MAX_PASSAGES = 6
PASSAGE_CHARS = 700
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
    # A yes/no "is this enough?" flag was unreliable on small models (set to
    # false for complete answers); naming what is missing is concrete.
    missing: str = Field(
        default="",
        description=(
            "Every part of the question the passages do not answer (a number, a date, "
            "a result, an outcome...), in one sentence. Empty only if every part is answered."
        ),
    )


_TERMS_SYSTEM = (
    "You help search a personal knowledge notebook written in Korean and English. "
    "Given a question, write up to 4 short keyword searches that would match notes "
    "answering it: include Korean and English forms, synonyms, abbreviations, and names "
    "of people, organizations, or things. Keywords only, no full sentences."
)

_ANSWER_SYSTEM = (
    "You answer questions using only the numbered passages from the user's own notes. "
    "Rules: use no outside knowledge; give each sentence the numbers of the passages it "
    "comes from; add no advice or predictions of your own. "
    "A question often asks several things (a number and a result, what and when): answer "
    "each part the passages cover, and name every part they do not cover in the missing "
    "field; leave it empty only if every part is answered. "
    "If passages give different dates or figures for the same thing, give each with its "
    "passage number and say which source is more recent; do not pick one silently. "
    "A passage marked 'unchallenged idea' or 'provisional idea' is the user's hypothesis, "
    "not an established fact: say so when you use it. A passage marked 'notes disagree' "
    "has a recorded conflict: mention it. "
    "Write every sentence in {language}, concisely: the direct answer first, then at most "
    "four supporting points."
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
    # What the notes don't cover, in the answer's language; empty if nothing.
    missing: str = ""
    model: str | None = None
    seconds: float = 0.0
    # True while the answer is still being written (streamed sentence by sentence).
    partial: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _excerpt(text: str, limit: int = 220) -> str:
    flat = " ".join(line.strip("-* ").strip() for line in text.splitlines() if line.strip())
    return flat if len(flat) <= limit else flat[: limit - 1].rstrip() + "…"


def gather(
    retriever: Retriever,
    question: str,
    provider: Provider | None,
    query_vec: Sequence[float] | None = None,
    limit: int = MAX_PASSAGES,
) -> tuple[list[Passage], float]:
    """Passages for ``question``.

    With meaning search (``query_vec``) one fused search is enough: it already
    matches other wording and the other language. Keyword-only search is
    widened with model-written search terms when its results are weak.
    """
    if query_vec is not None:
        hits = retriever.search(question, limit=limit, query_vec=query_vec)
        return [p for _, p in hits], 0.0
    hits = retriever.search(question, limit=limit)
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
            for score, p in retriever.search(query, limit=limit):
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
        hits = kept[:limit]
    return [p for _, p in hits], seconds


_STATUS_LABEL = {
    "candidate": "unchallenged idea",
    "provisional": "provisional idea",
    "established": "established idea",
}


def _meta(record: Record) -> str:
    """What the model should know about where a passage comes from."""
    meta = record.metadata
    if record.category == "insight":
        kind = _STATUS_LABEL.get((record.status or "").lower(), "idea")
    elif record.category == "source":
        kind = "source"
    elif record.category == "memory":
        kind = "the user's own memory"
    else:
        kind = "knowledge note"
    parts = [kind]
    published = meta.get("published")
    if published and str(published) != "unknown":
        parts.append(f"published {published}")
    elif meta.get("observed_at"):
        parts.append(f"noted {meta['observed_at']}")
    conflict = first_conflict(record.content)
    if conflict:
        parts.append(f"notes disagree: {conflict}")
    return ", ".join(parts)


def _prompt(question: str, found: list[Passage]) -> str:
    blocks = []
    for n, p in enumerate(found, 1):
        where = p.record.title + (f" — {p.heading}" if p.heading else "")
        meta = _meta(p.record)
        text = p.text.strip()
        if len(text) > PASSAGE_CHARS:
            text = text[:PASSAGE_CHARS].rsplit(" ", 1)[0] + " …"
        blocks.append(f"[{n}] {where} ({meta})\n{text}")
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


_DECODER = json.JSONDecoder()


def finished_statements(raw: str) -> list[dict[str, Any]]:
    """The statements already complete in a partly written answer.

    The model writes ``{"statements": [{...}, {...}`` one object at a time; each
    object that has closed is returned, so the answer can show up sentence by
    sentence while the rest is still being written.
    """
    start = raw.find('"statements"')
    if start < 0:
        return []
    out: list[dict[str, Any]] = []
    pos = raw.find("[", start)
    if pos < 0:
        return out
    pos += 1
    while True:
        brace = raw.find("{", pos)
        if brace < 0:
            break
        try:
            obj, end = _DECODER.raw_decode(raw, brace)
        except ValueError:
            break  # still being written
        if isinstance(obj, dict) and isinstance(obj.get("text"), str):
            out.append(obj)
        pos = end
    return out


def _lines(statements: Sequence[Any]) -> str:
    lines = []
    for i, s in enumerate(statements):
        sources = s.get("sources") if isinstance(s, dict) else s.sources
        text = (s.get("text") if isinstance(s, dict) else s.text) or ""
        text = text.strip()
        if not text:
            continue
        nums = [n for n in (sources or []) if isinstance(n, int)]
        marks = "".join(f"[{n}]" for n in dict.fromkeys(nums))
        lines.append(f"{'' if i == 0 else '- '}{text} {marks}".rstrip())
    return "\n".join(lines)


def ask(
    index: BrainIndex,
    question: str,
    provider: Provider,
    *,
    language: str,
    retriever: Retriever | None = None,
    query_vec: Sequence[float] | None = None,
    max_passages: int = MAX_PASSAGES,
    on_partial: Callable[[Answer], None] | None = None,
) -> Answer:
    """Answer ``question`` from the Brain.

    ``on_partial`` (optional) is called with a provisional Answer each time
    another sentence is finished, when the provider can stream.
    """
    question = question.strip()
    if not question:
        raise AskError("Empty question", "ask.empty")
    if len(question) > 1000:
        raise AskError("Question too long", "ask.too_long")
    retriever = retriever or Retriever(index)
    found, seconds = gather(retriever, question, provider, query_vec, max_passages)
    if not found:
        return Answer(question, "", found=False, seconds=seconds)

    language = answer_language(question, language)
    system = _ANSWER_SYSTEM.format(language=_LANGUAGE_NAME.get(language, "English"))

    shown = 0

    def on_text(raw: str) -> None:
        nonlocal shown
        done = finished_statements(raw)
        if len(done) > shown and on_partial is not None:
            shown = len(done)
            text, citations = _cite(_lines(done), found)
            on_partial(Answer(question, text, found=True, citations=citations, partial=True))

    # Only a caller that wants sentences early asks the provider to stream.
    extra: dict[str, Any] = {"on_text": on_text} if on_partial is not None else {}
    result = provider.generate_json(
        system, _prompt(question, found), AnswerDraft.model_json_schema(), **extra
    )
    try:
        draft = AnswerDraft.model_validate(result.data)
    except ValidationError as exc:
        raise AskError(str(exc), "ask.bad_shape") from exc
    text, citations = _cite(_lines(draft.statements), found)
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
            missing=draft.missing.strip(),
            model=result.model,
            seconds=seconds + result.seconds,
        )
    return Answer(
        question,
        text,
        found=not draft.missing.strip(),
        citations=citations,
        missing=draft.missing.strip(),
        model=result.model,
        seconds=seconds + result.seconds,
    )
