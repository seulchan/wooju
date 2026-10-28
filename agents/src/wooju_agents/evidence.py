"""Numbered passages of a source, and quotes rebuilt from them.

The model never copies a quote. It sees the source as numbered passages
("[12] ...") and names the passages that state a key point; the quote is then
cut from the original by code. A quote in a note is therefore always the
source's own words, character for character (whitespace aside). Whether the
passage really says what the point claims is still for the reader to judge;
the note shows both side by side so that is easy.

Long sources are read in parts that each fit the model's context, so a long
PDF is read to the end instead of only its first pages.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

MAX_PASSAGE_CHARS = 400
MIN_PASSAGE_CHARS = 20
MAX_QUOTE_PASSAGES = 3
MAX_QUOTE_CHARS = 900

_SENTENCE_END = re.compile(r"(?<=[.!?。！？…])[\"'”’)\]]*\s+(?=\S)")
_LINE_END = re.compile(r"[.!?。！？:;…\"'”’)]\s*$")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


def estimate_tokens(text: str) -> int:
    """Rough token count: Hangul is about a token per character, other text ~4 chars."""
    hangul = sum(1 for ch in text if "가" <= ch <= "힣")
    return hangul + (len(text) - hangul) // 4


_BLOCK_START = re.compile(r"^(?:[-•·*▪▢□■○●◦◆◇※§>]|\d+[.)]\s|\(\d+\)|[①-⑳]|#)")


def _paragraphs(text: str) -> list[str]:
    """Blocks of running text. A wrapped line (PDF) joins the next one; a line
    that ends a sentence, a heading-like short line, or a line followed by a
    list mark or heading does not."""
    out: list[str] = []
    for block in re.split(r"\n\s*\n", text):
        lines = [" ".join(raw.split()) for raw in block.split("\n")]
        lines = [line for line in lines if line]
        current = ""
        for i, line in enumerate(lines):
            current = f"{current} {line}" if current else line
            following = lines[i + 1] if i + 1 < len(lines) else ""
            if (
                not following
                or _LINE_END.search(line)
                or len(line) < 15
                or _BLOCK_START.match(following)
            ):
                out.append(current)
                current = ""
        if current:
            out.append(current)
    return out


def _cut(sentence: str) -> list[str]:
    """Split an over-long sentence at word boundaries."""
    pieces: list[str] = []
    while len(sentence) > MAX_PASSAGE_CHARS:
        at = sentence.rfind(" ", MAX_PASSAGE_CHARS // 2, MAX_PASSAGE_CHARS)
        at = at if at > 0 else MAX_PASSAGE_CHARS
        pieces.append(sentence[:at].strip())
        sentence = sentence[at:].strip()
    if sentence:
        pieces.append(sentence)
    return pieces


def passages(text: str) -> list[str]:
    """The source as passages of about a sentence; passage n is ``result[n - 1]``.

    A piece too short to stand alone (a heading, "Results") goes with what
    follows it.
    """
    out: list[str] = []
    pending = ""
    for para in _paragraphs(text):
        for sentence in _SENTENCE_END.split(para):
            for piece in _cut(sentence.strip()):
                joined = f"{pending} {piece}" if pending else piece
                if len(joined) < MIN_PASSAGE_CHARS:
                    pending = joined
                    continue
                if len(joined) <= MAX_PASSAGE_CHARS:
                    out.append(joined)
                else:
                    out += [pending, piece] if pending else [piece]
                pending = ""
    if pending:
        if out and len(out[-1]) + len(pending) < MAX_PASSAGE_CHARS:
            out[-1] = f"{out[-1]} {pending}"
        else:
            out.append(pending)
    return out


def render(items: list[str], part: range) -> str:
    """Passages ``part`` (0-based indexes) as the model reads them: ``[n] text``."""
    return "\n".join(f"[{i + 1}] {items[i]}" for i in part)


def parts(items: list[str], budget_tokens: int) -> list[range]:
    """Consecutive passages grouped so each group's rendering fits the budget."""
    groups: list[range] = []
    start, used = 0, 0
    for i, passage in enumerate(items):
        cost = estimate_tokens(f"[{i + 1}] {passage}\n") + 1  # +1: rounding
        if i > start and used + cost > budget_tokens:
            groups.append(range(start, i))
            start, used = i, 0
        used += cost
    if start < len(items):
        groups.append(range(start, len(items)))
    return groups


@dataclass(frozen=True)
class Quote:
    first: int  # passage numbers, 1-based, inclusive
    last: int
    text: str


def quote(items: list[str], part: range, first: object, last: object) -> Quote | None:
    """The quote for passages ``first``..``last``, or None if they are not a short
    run of passages inside ``part``."""
    if not isinstance(first, int) or isinstance(first, bool):
        return None
    if last is None:
        last = first
    if not isinstance(last, int) or isinstance(last, bool):
        return None
    if not (part.start + 1 <= first <= last <= part.stop):
        return None
    if last - first + 1 > MAX_QUOTE_PASSAGES:
        return None
    text = " ".join(items[first - 1 : last])
    if not text.strip() or len(text) > MAX_QUOTE_CHARS:
        return None
    return Quote(first, last, text)


def _numbers(text: str) -> set[str]:
    return {n.replace(",", "") for n in _NUMBER.findall(text)}


def numbers_found(point: str, quoted: str) -> bool:
    """Every number the point states also appears in the quote.

    Numbers are where a summary most often drifts from its source ("75%" that
    the passage does not say), and the one thing code can check cheaply.
    """
    return _numbers(point) <= _numbers(quoted)
