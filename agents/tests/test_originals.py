from __future__ import annotations

import re
from pathlib import Path

import pytest

from brain_core.index import BrainIndex
from wooju_agents.ask import ask
from wooju_agents.llm import LLMResult
from wooju_agents.originals import excerpts, library_reader, original_path
from wooju_agents.text import extract_text

NOTE = """---
title: Korea Value-up Index starts
source_type: article
canonical_ref: https://example.com/value-up
published: 2024-09-24
---
# Korea Value-up Index starts

## Key Ideas

- The index has 100 constituents.
  > The index has 100 constituents.

## Original

- [Original file](../library/value-up.txt)
"""

ORIGINAL = (
    "The Korea Exchange will publish the Korea Value-up Index. The index has 100 "
    "constituents. Companies were picked on profitability and shareholder returns. "
    "Futures tracking the index start trading in November. "
    + "Unrelated market colour about the weather in Busan. " * 20
    + "The cut-off for return on equity was the top half of each industry."
)


@pytest.fixture
def brain(tmp_path: Path) -> Path:
    (tmp_path / "sources").mkdir()
    (tmp_path / "library").mkdir()
    (tmp_path / "sources" / "value-up.md").write_text(NOTE, encoding="utf-8")
    (tmp_path / "library" / "value-up.txt").write_text(ORIGINAL, encoding="utf-8")
    return tmp_path


def index_of(brain: Path) -> BrainIndex:
    i = BrainIndex()
    i.scan(brain)
    return i


def read(brain: Path):
    return library_reader(brain, lambda p: extract_text(p, max_chars=200_000)[0])


class Provider:
    """First the notes' answer (with a missing part), then the originals' answer."""

    name, model = "fake", "fake-1"

    def __init__(self, notes, original):
        self.replies, self.calls = [notes, original], []

    def generate_json(self, system, user, schema, on_text=None):
        self.calls.append((system, user, schema))
        if "queries" in schema["properties"]:
            return LLMResult({"queries": ["value-up"]}, "", 0.01, self.name, self.model)
        reply = self.replies.pop(0)
        data = reply(user) if callable(reply) else reply
        return LLMResult(data, "", 0.5, self.name, self.model)


def say(*statements, missing=""):
    return {"statements": [{"text": s, "sources": n} for s, n in statements], "missing": missing}


def test_the_original_answers_what_the_notes_left_out(brain):
    question = "What was the return on equity cut-off for the value-up index?"

    def original_reply(user):
        n = int(re.search(r"\[(\d+)\] [^\n]*\(original\)\n[^\n]*cut-off", user).group(1))
        return say(("The cut-off was the top half of each industry.", [n]))

    provider = Provider(
        say(
            ("The index has 100 constituents.", [1]), missing="The ROE cut-off is not in the notes."
        ),
        original_reply,
    )
    partials = []
    answer = ask(
        index_of(brain),
        question,
        provider,
        language="en",
        read_original=read(brain),
        on_partial=partials.append,
    )
    assert answer.missing  # the notes' answer still says what they lacked
    assert answer.original_answer == "The cut-off was the top half of each industry. [2]"
    [c] = answer.original_citations
    assert c.n == 2 and c.category == "original" and c.id == "sources/value-up"
    assert "top half of each industry" in c.excerpt and c.excerpt in ORIGINAL
    assert partials and partials[-1].checking_originals and partials[-1].partial
    system, user, _ = provider.calls[-1]
    assert "about the notes, not about these excerpts" in system
    assert user.endswith("What the notes lacked: The ROE cut-off is not in the notes.")


def test_a_complete_answer_does_not_read_the_originals(brain):
    provider = Provider(say(("It has 100 constituents.", [1])), None)
    answer = ask(
        index_of(brain),
        "How many constituents?",
        provider,
        language="en",
        read_original=read(brain),
    )
    answers = [c for c in provider.calls if "queries" not in c[2]["properties"]]
    assert answer.original_answer == "" and len(answers) == 1


def test_when_the_originals_do_not_answer_it_says_so(brain):
    provider = Provider(
        say(("It has 100 constituents.", [1]), missing="The listing date is not covered."),
        say(missing="The listing date is not in the originals either."),
    )
    answer = ask(
        index_of(brain),
        "At what price did the futures start trading?",
        provider,
        language="en",
        read_original=read(brain),
    )
    assert answer.original_answer == "" and answer.original_citations == []
    assert answer.original_missing == "The listing date is not in the originals either."


def test_only_files_inside_the_library_are_read(brain, tmp_path):
    reader = read(brain)
    (brain / "secret.txt").write_text("private", encoding="utf-8")
    assert reader("library/value-up.txt")
    assert reader("library/../secret.txt") is None
    assert reader("library/missing.txt") is None


def test_original_path_and_excerpts(brain):
    record = index_of(brain).get("sources/value-up")
    assert original_path(record) == "library/value-up.txt"
    picked = excerpts("return on equity cut-off", [(record, ORIGINAL)])
    assert "top half of each industry" in picked[0].text
    assert all(e.text in ORIGINAL for e in picked)


def test_korean_terms_match_with_particles():
    from wooju_agents.originals import _terms

    assert "금리" in _terms("기준금리를") and "금리" in _terms("금리는")


def test_a_question_in_another_language_gets_search_terms_first(tmp_path):
    (tmp_path / "sources").mkdir()
    (tmp_path / "library").mkdir()
    (tmp_path / "sources" / "value-up.md").write_text(NOTE, encoding="utf-8")
    (tmp_path / "library" / "value-up.txt").write_text(ORIGINAL, encoding="utf-8")

    def original_reply(user):
        n = int(re.search(r"\[(\d+)\] [^\n]*\(original\)\n[^\n]*cut-off", user).group(1))
        return say(("업종 상위 절반이 기준이었어요.", [n]))

    class Terms(Provider):
        def generate_json(self, system, user, schema, on_text=None):
            if "queries" in schema["properties"] and len(self.calls) > 1:
                self.calls.append((system, user, schema))
                return LLMResult({"queries": ["return on equity cut-off"]}, "", 0.1, "f", "f")
            return super().generate_json(system, user, schema, on_text)

    provider = Terms(
        say(("구성종목은 100개예요.", [1]), missing="ROE 기준은 노트에 없어요."), original_reply
    )
    answer = ask(
        index_of(tmp_path),
        "밸류업 지수의 자기자본이익률 기준은 뭐였어?",
        provider,
        language="ko",
        read_original=read(tmp_path),
    )
    assert answer.original_answer.startswith("업종 상위 절반이 기준이었어요.")
    assert "top half of each industry" in answer.original_citations[0].excerpt


def test_a_rare_word_outweighs_common_ones():
    """A menu line full of "Bank of Korea / 한국은행" must not beat the one passage
    that names the thing asked about."""
    from brain_core.records import Record

    record = Record.__new__(Record)
    text = "\n\n".join(
        ["Bank of Korea 한국은행 Headquarters Seoul Central bank of Korea website."] * 30
        + ["BOK-Wire was renamed BOK-Wire+ in April 2009, when a hybrid system was added."]
    )
    picked = excerpts(
        "한국은행 BOK-Wire+는 언제 도입됐어? Bank of Korea BOK-Wire+ launch", [(record, text)]
    )
    assert "April 2009" in picked[0].text
