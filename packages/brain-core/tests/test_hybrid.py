"""Keyword + meaning search, with hand-made vectors standing in for a model."""

from pathlib import Path

from brain_core.index import BrainIndex
from brain_core.retrieve import Retriever
from brain_core.vectors import VectorCache, normalize

TOPICS = [("밸류업", "value-up"), ("주가순자산", "book value", "pbr"), ("환율", "exchange rate")]


def fake_embed(text: str) -> list[float]:
    low = text.lower()
    return [sum(low.count(w) for w in words) + 0.01 for words in TOPICS]


def _brain(tmp_path: Path) -> BrainIndex:
    (tmp_path / "wiki" / "concepts").mkdir(parents=True)
    (tmp_path / "wiki" / "concepts" / "pbr.md").write_text(
        "---\ntitle: 주가순자산비율\n---\n# 주가순자산비율\n\n## 정의\n\n주가를 주당순자산으로 나눈 값. 코스피 종목 다수가 1배 미만이다.\n",
        encoding="utf-8",
    )
    (tmp_path / "wiki" / "concepts" / "fx.md").write_text(
        "---\ntitle: 환율\n---\n# 환율\n\n## 정의\n\n원/달러 환율은 수출 기업 실적에 영향을 준다.\n",
        encoding="utf-8",
    )
    index = BrainIndex()
    index.scan(tmp_path)
    return index


def test_english_question_finds_korean_note_by_meaning(tmp_path):
    retriever = Retriever(_brain(tmp_path))
    question = "Why do Korean stocks trade below book value?"
    assert retriever.search(question) == []  # no shared words

    cache = VectorCache(tmp_path / "v.sqlite", "fake")
    missing = retriever.load_vectors(cache)
    cache.put_many([(k, fake_embed(text)) for k, text in missing])
    assert retriever.load_vectors(cache) == []
    assert retriever.vector_coverage == (2, 2)

    hits = retriever.search(question, query_vec=normalize(fake_embed(question)))
    assert hits[0][1].id == "wiki/concepts/pbr"


def test_unchanged_passages_are_not_embedded_again(tmp_path):
    index = _brain(tmp_path)
    cache = VectorCache(tmp_path / "v.sqlite", "fake")
    first = Retriever(index).load_vectors(cache)
    cache.put_many([(k, fake_embed(t)) for k, t in first])
    (tmp_path / "wiki" / "concepts" / "fx.md").write_text(
        "---\ntitle: 환율\n---\n# 환율\n\n## 정의\n\n원/달러 환율이 바뀌었다.\n", encoding="utf-8"
    )
    index.scan(tmp_path)
    again = Retriever(index).load_vectors(cache)
    assert len(again) == 1 and "바뀌었다" in again[0][1]


def test_other_model_has_its_own_keys(tmp_path):
    a = VectorCache(tmp_path / "v.sqlite", "model-a")
    b = VectorCache(tmp_path / "v.sqlite", "model-b")
    a.put_many([(a.key("x"), [1.0, 0.0])])
    assert b.get_many([b.key("x")]) == {}
