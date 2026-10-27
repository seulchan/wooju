"""Ranked passage retrieval for questions (Ask, Challenger, and the Claude connection).

:meth:`BrainIndex.search` needs every word to appear, which suits a search box
but not a question ("밸류업 지수에 어떤 기업이 들어갔어?"). This module splits notes
into passages (one per ``##`` section) and ranks them with BM25, so a passage
matching most of the important words wins even if some words are missing.

Korean words carry particles (지수에, 기업이), so Hangul words are matched by
their stem with common particles removed, and by character bigrams, which also
matches compound words written with or without spaces. Everything is computed
in memory from the current index; nothing is written to disk.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from .index import BrainIndex
from .records import Record
from .vectors import VectorCache, cosine

_RRF_K = 60
_CANDIDATES = 50
# Below this cosine similarity a passage is not a meaning match at all.
_MIN_COSINE = 0.35

_K1 = 1.4
_B = 0.75
_MAX_PASSAGE = 1500
_WORD = re.compile(r"[0-9a-zA-Z가-힣]+(?:[.'][0-9a-zA-Z]+)*")
_HANGUL = re.compile(r"[가-힣]")
# Longest first, so 에서는 is removed before 는.
_PARTICLES = sorted(
    """은 는 이 가 을 를 의 에 에서 에게 한테 께 로 으로 와 과 도 만 까지 부터 보다 처럼
    이나 나 이랑 랑 하고 에서는 에는 으로는 로는 이란 란 이라는 라는 이에요 예요 입니다
    인가요 인가 일까 일까요 이야 야 있어 있나요 했어 했나요 해줘 알려줘 인지 는지 은지""".split(),
    key=len,
    reverse=True,
)
_STOP = {
    # English question and function words
    "a",
    "an",
    "the",
    "of",
    "to",
    "in",
    "on",
    "for",
    "and",
    "or",
    "is",
    "are",
    "was",
    "were",
    "be",
    "do",
    "does",
    "did",
    "what",
    "which",
    "who",
    "whom",
    "how",
    "why",
    "when",
    "where",
    "about",
    "with",
    "my",
    "me",
    "i",
    "you",
    "it",
    "this",
    "that",
    "there",
    "any",
    "tell",
    "show",
    "know",
    "have",
    "has",
    "can",
    "could",
    "should",
    "would",
    "much",
    "many",
    # Korean question words and fillers (after particle removal)
    "무엇",
    "뭐",
    "뭔가",
    "어떤",
    "어떻게",
    "왜",
    "언제",
    "어디",
    "누구",
    "얼마",
    "얼마나",
    "그",
    "이",
    "저",
    "것",
    "거",
    "좀",
    "내",
    "나",
    "제",
    "있는",
    "있었",
    "대해",
    "대한",
    "관련",
    "알려",
    "말해",
    "설명",
    "정리",
    "무슨",
}


@dataclass(frozen=True)
class Passage:
    record: Record
    heading: str | None
    text: str

    @property
    def id(self) -> str:
        return self.record.id

    def embedding_text(self) -> str:
        """What gets embedded: where the passage is, then what it says."""
        where = self.record.title + (f" — {self.heading}" if self.heading else "")
        return f"{where}\n{self.text}"


def _strip_particle(word: str) -> str:
    for p in _PARTICLES:
        if len(word) > len(p) + 1 and word.endswith(p):
            return word[: -len(p)]
    return word


def tokens(text: str) -> list[str]:
    """Search terms for ``text``: words, Korean stems, and Korean bigrams."""
    out: list[str] = []
    for raw in _WORD.findall(text.lower()):
        if _HANGUL.search(raw):
            stem = _strip_particle(raw)
            if stem in _STOP or raw in _STOP:
                continue
            out.append(stem)
            if len(stem) > 2:
                out.extend(stem[i : i + 2] for i in range(len(stem) - 1))
        elif raw not in _STOP and (len(raw) > 1 or raw.isdigit()):
            out.append(raw)
    return out


_LINK_ONLY = re.compile(
    r"^\s*(?:[-*]\s*)?(?:\[\[[^\]]+\]\]|\[[^\]]*\]\([^)]*\))(?:\s*[,·]?\s*"
    r"(?:\[\[[^\]]+\]\]|\[[^\]]*\]\([^)]*\)))*\s*$"
)


def is_link_list(text: str) -> bool:
    """A section that only lists links ("Related", "관련 지식"): navigation, no content.

    Such sections matched questions by title words and took answer slots
    without saying anything (seen in evals/ask_quality.py), so they rank low:
    still a last resort when nothing else matches (an English question whose
    only English words are a link's title), never ahead of real content.
    """
    lines = [line for line in text.splitlines() if line.strip()]
    return bool(lines) and all(_LINK_ONLY.match(line) for line in lines)


LINK_LIST_WEIGHT = 0.3


def passages(record: Record) -> list[Passage]:
    """Split a note into passages at ``##`` headings, capped in length."""
    parts: list[Passage] = []
    heading: str | None = None
    buf: list[str] = []

    def flush() -> None:
        text = "\n".join(buf).strip()
        if text:
            for start in range(0, len(text), _MAX_PASSAGE):
                parts.append(Passage(record, heading, text[start : start + _MAX_PASSAGE]))

    for line in record.content.splitlines():
        m = re.match(r"^(#{1,3})\s+(.*)", line)
        if m and len(m.group(1)) >= 2:
            flush()
            heading, buf = m.group(2).strip(), []
        elif m:
            continue  # the note title; already part of every passage's score
        else:
            buf.append(line)
    flush()
    if not parts and record.title:
        parts.append(Passage(record, None, record.title))
    return parts


class Retriever:
    """BM25 over passages of one index snapshot. Rebuild after the index changes."""

    def __init__(self, index: BrainIndex) -> None:
        self.indexed_at = index.indexed_at
        self._passages: list[Passage] = []
        self._vectors: list[Sequence[float] | None] = []
        # (key, text) of passages without a vector; None until vectors are loaded.
        self.pending: list[tuple[str, str]] | None = None
        self._tf: list[Counter[str]] = []
        self._len: list[int] = []
        df: Counter[str] = Counter()
        for record in index.all_records():
            if record.category == "other" or record.retired:
                continue  # retired notes are never grounds for an answer
            head = " ".join([record.title, *record.aliases])
            for passage in passages(record):
                # The title counts twice, so a note about the subject outranks
                # one that merely mentions it.
                terms = tokens(f"{head} {head} {passage.heading or ''} {passage.text}")
                tf = Counter(terms)
                self._passages.append(passage)
                self._tf.append(tf)
                self._len.append(len(terms))
                df.update(tf.keys())
        n = max(len(self._passages), 1)
        self._avg = (sum(self._len) / n) or 1.0
        self._idf = {t: math.log(1 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items()}
        self._vectors = [None] * len(self._passages)
        self._weight = [LINK_LIST_WEIGHT if is_link_list(p.text) else 1.0 for p in self._passages]

    # ---------------------------------------------------------------- vectors

    def load_vectors(self, cache: VectorCache) -> list[tuple[str, str]]:
        """Attach cached vectors; return ``(key, text)`` for passages still missing one."""
        keys = [cache.key(p.embedding_text()) for p in self._passages]
        found = cache.get_many(keys)
        missing: dict[str, str] = {}
        for i, (key, p) in enumerate(zip(keys, self._passages, strict=True)):
            self._vectors[i] = found.get(key)
            if key not in found:
                missing.setdefault(key, p.embedding_text())
        self.pending = list(missing.items())
        return self.pending

    @property
    def vector_coverage(self) -> tuple[int, int]:
        """(passages with a vector, all passages)."""
        return sum(v is not None for v in self._vectors), len(self._vectors)

    def _bm25(self, query: str) -> list[tuple[float, int]]:
        q = list(dict.fromkeys(tokens(query)))
        if not q:
            return []
        scored: list[tuple[float, int]] = []
        for i, tf in enumerate(self._tf):
            score = 0.0
            for term in q:
                f = tf.get(term)
                if f:
                    norm = f + _K1 * (1 - _B + _B * self._len[i] / self._avg)
                    score += self._idf.get(term, 0.0) * f * (_K1 + 1) / norm
            if score > 0:
                scored.append((score * self._weight[i], i))
        scored.sort(key=lambda s: (-s[0], self._passages[s[1]].record.path))
        return scored

    def _semantic(self, query_vec: Sequence[float]) -> list[tuple[float, int]]:
        scored = [
            (cosine(query_vec, v) * self._weight[i], i)
            for i, v in enumerate(self._vectors)
            if v is not None
        ]
        scored = [s for s in scored if s[0] >= _MIN_COSINE]
        scored.sort(key=lambda s: (-s[0], self._passages[s[1]].record.path))
        return scored

    def search(
        self,
        query: str,
        limit: int = 8,
        per_note: int = 2,
        query_vec: Sequence[float] | None = None,
    ) -> list[tuple[float, Passage]]:
        """Best passages for ``query``, at most ``per_note`` from the same note.

        With ``query_vec`` (the query's normalized embedding) and passage
        vectors loaded, keyword and meaning rankings are fused (reciprocal rank
        fusion), so a passage that says the same thing in other words, or in
        the other language, is found too. Scores are then fusion scores.
        """
        keyword = self._bm25(query)
        if query_vec is not None and any(v is not None for v in self._vectors):
            fused: dict[int, float] = {}
            for ranked in (keyword[:_CANDIDATES], self._semantic(query_vec)[:_CANDIDATES]):
                for rank, (_, i) in enumerate(ranked):
                    fused[i] = fused.get(i, 0.0) + 1.0 / (_RRF_K + rank + 1)
            scored = sorted(
                ((s, i) for i, s in fused.items()),
                key=lambda s: (-s[0], self._passages[s[1]].record.path),
            )
        else:
            scored = keyword
        out: list[tuple[float, Passage]] = []
        seen: Counter[str] = Counter()
        for score, i in scored:
            p = self._passages[i]
            if seen[p.id] >= per_note:
                continue
            seen[p.id] += 1
            out.append((score, p))
            if len(out) >= limit:
                break
        return out


class RetrieverCache:
    """Reuses one :class:`Retriever` until the index is rescanned."""

    def __init__(self) -> None:
        self._retriever: Retriever | None = None

    def get(self, index: BrainIndex) -> Retriever:
        if self._retriever is None or self._retriever.indexed_at != index.indexed_at:
            self._retriever = Retriever(index)
        return self._retriever
