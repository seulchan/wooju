from pathlib import Path

import pytest

from brain_core.index import BrainIndex
from wooju_agents.ask import AskError, ask
from wooju_agents.llm import LLMResult


class ScriptedProvider:
    """Returns one scripted reply per call, keyed by the schema's fields."""

    name, model = "fake", "fake-1"

    def __init__(self, answer=None, queries=None):
        self.answer, self.queries, self.calls = answer, queries, []

    def generate_json(self, system, user, schema):
        self.calls.append((system, user, schema))
        if "queries" in schema["properties"]:
            return LLMResult({"queries": self.queries or ["x"]}, "", 0.01, self.name, self.model)
        return LLMResult(self.answer, "", 0.5, self.name, self.model)


@pytest.fixture
def index(tmp_path: Path) -> BrainIndex:
    (tmp_path / "sources").mkdir()
    (tmp_path / "memory" / "records").mkdir(parents=True)
    (tmp_path / "sources" / "value-up.md").write_text(
        "---\ntitle: 코리아 밸류업 지수 발표\nsource_type: news\ncanonical_ref: x\n"
        "published: 2024-09-24\n---\n# 코리아 밸류업 지수 발표\n\n## 핵심 내용\n\n"
        "- 밸류업 지수 구성종목은 100개다.\n- 삼성전자와 SK하이닉스가 포함됐다.\n",
        encoding="utf-8",
    )
    (tmp_path / "sources" / "kospi-pbr.md").write_text(
        "---\ntitle: 코스피 PBR 분석\nsource_type: report\ncanonical_ref: y\n---\n"
        "# 코스피 PBR 분석\n\n## 핵심 내용\n\n- 코스피 종목의 75%가 PBR 1배 미만이다.\n",
        encoding="utf-8",
    )
    (tmp_path / "memory" / "records" / "principle.md").write_text(
        "---\ntitle: 투자 원칙\ntype: preference\nprovenance: stated\n---\n# 투자 원칙\n\n"
        "## 내용\n\n저평가 기업의 재평가를 본다.\n",
        encoding="utf-8",
    )
    i = BrainIndex()
    i.scan(tmp_path)
    return i


def say(*statements, missing=""):
    return {"statements": [{"text": s, "sources": n} for s, n in statements], "missing": missing}


def test_answer_cites_passages_and_renumbers(index):
    provider = ScriptedProvider(
        answer=say(("구성종목은 100개예요.", [1]), ("삼성전자가 포함됐어요.", [1, 9]))
    )
    result = ask(index, "밸류업 지수 구성종목은 몇 개야?", provider, language="en")
    assert result.found
    # The invalid [9] is dropped; the first sentence is the direct answer.
    assert result.answer == "구성종목은 100개예요. [1]\n- 삼성전자가 포함됐어요. [1]"
    assert [c.id for c in result.citations] == ["sources/value-up"]
    system, user, _ = provider.calls[-1]
    assert "Korean" in system and "[1] 코리아 밸류업" in user and "2024-09-24" in user


def test_citations_renumber_in_reading_order(index):
    provider = ScriptedProvider(answer=say(("A.", [2]), ("B.", [1])))
    result = ask(index, "밸류업 지수 PBR 코스피", provider, language="en")
    user = provider.calls[-1][1]
    second = user.split("[2] ")[1].split(" (")[0].split(" — ")[0]
    assert result.answer == "A. [1]\n- B. [2]"
    assert result.citations[0].title == second
    assert [c.n for c in result.citations] == [1, 2]


def test_missing_part_is_reported(index):
    provider = ScriptedProvider(
        answer=say(("구성종목은 100개예요.", [1]), missing="편입 기준은 노트에 없어요.")
    )
    result = ask(index, "밸류업 지수 구성종목과 편입 기준은?", provider, language="ko")
    assert not result.found and result.missing == "편입 기준은 노트에 없어요."
    assert result.citations


def test_uncited_answer_shows_what_was_read(index):
    provider = ScriptedProvider(answer=say(("100개예요.", [7])))
    result = ask(index, "밸류업 지수 구성종목은 몇 개야?", provider, language="ko")
    assert not result.found and result.related_only
    assert result.answer == "100개예요."
    assert result.citations[0].id == "sources/value-up"


def test_answers_in_the_question_language(index):
    provider = ScriptedProvider(answer=say(("x", [1])))
    ask(index, "밸류업 지수 구성종목은 몇 개야?", provider, language="en")
    assert "in Korean" in provider.calls[-1][0]
    ask(index, "What share of KOSPI stocks have a PBR below 1?", provider, language="ko")
    assert "in English" in provider.calls[-1][0]


def test_nothing_relevant_calls_model_only_for_search_terms(index):
    provider = ScriptedProvider(queries=["bitcoin", "비트코인"])
    result = ask(index, "How is bitcoin mining doing?", provider, language="en")
    assert not result.found and result.answer == ""
    assert len(provider.calls) == 1  # only the search-term call


def test_weak_question_is_widened_with_model_terms(index):
    provider = ScriptedProvider(
        queries=["PBR", "주가순자산비율"],
        answer=say(("75% trade below book.", [1])),
    )
    result = ask(index, "How many stocks trade below book value?", provider, language="en")
    assert result.found
    assert result.citations[0].id == "sources/kospi-pbr"
    assert len(provider.calls) == 2


def test_empty_question(index):
    with pytest.raises(AskError) as err:
        ask(index, "  ", ScriptedProvider(), language="en")
    assert err.value.key == "ask.empty"


def test_meaning_search_skips_the_search_terms_call(index):
    from brain_core.retrieve import Retriever
    from brain_core.vectors import VectorCache, normalize

    retriever = Retriever(index)
    import tempfile
    from pathlib import Path

    cache = VectorCache(Path(tempfile.mkdtemp()) / "v.sqlite", "fake")
    cache.put_many(
        [(k, [1.0, 0.0] if "PBR" in t else [0.0, 1.0]) for k, t in retriever.load_vectors(cache)]
    )
    retriever.load_vectors(cache)
    provider = ScriptedProvider(answer=say(("75% trade below book.", [1])))
    result = ask(
        index,
        "How many stocks trade below book value?",
        provider,
        language="en",
        retriever=retriever,
        query_vec=normalize([1.0, 0.0]),
    )
    assert result.citations[0].id == "sources/kospi-pbr"
    assert len(provider.calls) == 1  # no search-terms call


def test_finished_statements_appear_one_by_one():
    from wooju_agents.ask import finished_statements

    raw = '{"statements": [{"text": "First.", "sources": [1]}, {"text": "Sec'
    assert [s["text"] for s in finished_statements(raw)] == ["First."]
    raw += 'ond.", "sources": [2, 1]}], "missing": ""}'
    assert [s["text"] for s in finished_statements(raw)] == ["First.", "Second."]
    assert finished_statements('{"statem') == []


class StreamingProvider(ScriptedProvider):
    """Writes the answer in pieces, like Ollama does, when asked to stream."""

    def generate_json(self, system, user, schema, on_text=None):
        if "queries" in schema["properties"]:
            return super().generate_json(system, user, schema)
        import json

        raw = json.dumps(self.answer, ensure_ascii=False)
        if on_text is not None:
            for cut in range(1, len(raw) + 1, 7):
                on_text(raw[:cut])
            on_text(raw)
        return LLMResult(self.answer, raw, 0.5, self.name, self.model)


def test_sentences_arrive_while_the_answer_is_written(index):
    provider = StreamingProvider(
        answer=say(("구성종목은 100개예요.", [1]), ("삼성전자가 포함됐어요.", [1]))
    )
    seen = []
    result = ask(
        index, "밸류업 지수 구성종목은 몇 개야?", provider, language="en", on_partial=seen.append
    )
    assert [a.answer for a in seen] == [
        "구성종목은 100개예요. [1]",
        "구성종목은 100개예요. [1]\n- 삼성전자가 포함됐어요. [1]",
    ]
    assert all(a.partial and a.citations for a in seen)
    assert not result.partial and result.answer == seen[-1].answer


def test_the_model_is_told_what_each_passage_is(tmp_path):
    from brain_core.index import BrainIndex as Index
    from brain_core.retrieve import Retriever as R
    from wooju_agents.ask import _prompt, gather

    (tmp_path / "sources").mkdir()
    (tmp_path / "wiki" / "questions").mkdir(parents=True)
    (tmp_path / "sources" / "rate.md").write_text(
        "---\ntitle: 금리 인상\nsource_type: article\ncanonical_ref: x\npublished: 2026-07-16\n---\n"
        "# 금리 인상\n\n## 핵심 내용\n\n- 기준금리를 2.75%로 올렸다.\n\n## Conflicts\n\n"
        "- 다른 노트는 2024년에 이미 2.75%였다고 한다.\n",
        encoding="utf-8",
    )
    (tmp_path / "wiki" / "questions" / "idea.md").write_text(
        "---\ntitle: 금리와 은행주\norigin: synthesis\ninsight_kind: hypothesis\nstatus: candidate\n"
        "derived_from: ['[x](../../sources/rate.md)']\n---\n# 금리와 은행주\n\n## Insight\n\n기준금리가 오르면 은행주가 오른다.\n",
        encoding="utf-8",
    )
    i = Index()
    i.scan(tmp_path)
    found, _ = gather(R(i), "기준금리", None)
    prompt = _prompt("기준금리", found)
    assert (
        "(source, published 2026-07-16, notes disagree: 다른 노트는 2024년에 이미 2.75%였다고 한다.)"
        in prompt
    )
    assert "(unchallenged idea)" in prompt
