from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest

from brain_core import history
from brain_core.changes import apply_proposal
from brain_core.validate import validate_brain
from wooju_agents.ingest import (
    IngestError,
    SourceDraft,
    estimate_tokens,
    inbox_files,
    ingest_file,
    slugify,
)
from wooju_agents.llm import LLMResult

ARTICLE = """KOSPI 75% below book value (Seoul Economic Daily, 2026-07-29)
https://en.sedaily.com/finance/2026/07/29/75-percent-of-kospi-stocks
75% of KOSPI stocks trade below book value as the correction deepens. 600 of 802 stocks.
"""


def passage_with(user: str, needle: str) -> int:
    """The number of the passage the model was shown that contains ``needle``."""
    for line in user.splitlines():
        m = re.match(r"\[(\d+)\] (.*)", line)
        if m and needle in m.group(2):
            return int(m.group(1))
    return 999  # not shown: a reference that cannot be checked


class FakeProvider:
    """Answers by schema. Key points in ``data`` cite by text: ``{"text", "cite"}``."""

    name, model = "fake", "fake-1"

    def __init__(self, data, fixes=None):
        self.data, self.fixes, self.calls = data, fixes or [], []

    def answer(self, schema_title, user):
        if schema_title == "Fixes":
            return {"fixes": self.fixes}
        out = dict(self.data)
        if "key_points" in out:
            out["key_points"] = [
                {"text": p["text"], "first": (n := passage_with(user, p["cite"])), "last": n}
                if "cite" in p
                else p
                for p in out["key_points"]
            ]
        return out

    def generate_json(self, system, user, schema):
        self.calls.append((system, user, schema))
        return LLMResult(self.answer(schema.get("title"), user), "", 0.01, self.name, self.model)


DRAFT = {
    "title": "75% of KOSPI Stocks Trade Below Book Value",
    "source_type": "article",
    "authors": ["Seoul Economic Daily", " "],
    "published": "2026-07-29",
    "one_line_summary": "2026 년 7 월 29 일 코스피 종목의 75%가 PBR 1 배 미만이다.",
    "key_points": [{"text": "802 개 중 600 개 종목", "cite": "600 of 802"}],
    "limitations": ["업종별 수치는 없다."],
}


def POINT(needle: str) -> dict[str, str]:  # noqa: N802 — reads like a constant in drafts
    return {"text": f"About {needle}", "cite": needle}


@pytest.fixture
def brain(make_brain):
    b = make_brain({"inbox/clip.txt": ARTICLE, "inbox/.DS_Store": "x", "inbox/photo.heic": "x"})
    history.ensure_repo(b)
    return b


def test_inbox_lists_only_supported_visible_files(brain):
    assert inbox_files(brain) == ["inbox/clip.txt"]


def test_ingest_builds_a_valid_auto_proposal(brain):
    provider = FakeProvider(DRAFT)
    p = ingest_file(brain, "inbox/clip.txt", provider, language="ko", today=date(2026, 10, 26))
    assert p.approval == "auto" and p.status == "pending"
    assert [c.op for c in p.changes] == ["write", "copy", "delete"]
    note = p.changes[0].content
    assert p.changes[0].path == "sources/75-of-kospi-stocks-trade-below-book-value.md"
    assert (
        "canonical_ref: https://en.sedaily.com/finance/2026/07/29/75-percent-of-kospi-stocks"
        in note
    )
    assert "accessed: '2026-10-26'" in note
    assert "2026년 7월 29일" in note and "PBR 1배" in note and "802개 중 600개" in note
    assert "## 한 줄 요약" in note and "## 원본" in note
    assert "Korean" in provider.calls[0][0]
    assert p.summary.startswith("2026년 7월")

    applied = apply_proposal(brain, p)
    assert applied.status == "applied", applied.error
    assert not (brain / "inbox/clip.txt").exists()
    assert (brain / "library/75-of-kospi-stocks-trade-below-book-value.txt").exists()
    assert validate_brain(brain).ok


def test_unknown_date_and_bad_date_become_unknown(brain):
    p = ingest_file(
        brain, "inbox/clip.txt", FakeProvider({**DRAFT, "published": "last summer"}), language="en"
    )
    assert "published: unknown" in p.changes[0].content
    assert "## One-line Summary" in p.changes[0].content


def test_no_url_falls_back_to_library_copy(make_brain):
    b = make_brain(
        {"inbox/notes.md": "A long enough text about value-up disclosures without any link at all."}
    )
    p = ingest_file(
        b,
        "inbox/notes.md",
        FakeProvider({**DRAFT, "title": "가치 제고 메모", "key_points": [POINT("value-up")]}),
        language="ko",
    )
    note_path = p.changes[0].path
    assert note_path == "sources/notes.md"  # Korean title has no ASCII slug → file name
    assert "canonical_ref: library/notes.md" in p.changes[0].content


def test_name_collisions_get_a_suffix(brain):
    (brain / "sources").mkdir()
    (brain / "sources/75-of-kospi-stocks-trade-below-book-value.md").write_text("x")
    p = ingest_file(brain, "inbox/clip.txt", FakeProvider(DRAFT), language="en")
    assert p.changes[0].path.endswith("-2.md")


def test_model_output_that_breaks_the_shape_is_refused(brain):
    with pytest.raises(IngestError) as exc:
        ingest_file(brain, "inbox/clip.txt", FakeProvider({"title": "x"}), language="en")
    assert "형식" in exc.value.user_message


def test_invalid_source_type_is_refused(brain):
    with pytest.raises(IngestError):
        ingest_file(
            brain, "inbox/clip.txt", FakeProvider({**DRAFT, "source_type": "tweet"}), language="en"
        )


def test_paths_outside_inbox_are_refused(brain):
    with pytest.raises(IngestError):
        ingest_file(brain, "sources/x.md", FakeProvider(DRAFT), language="en")


def test_unsupported_and_empty_files(make_brain):
    b = make_brain({"inbox/a.docx": "x", "inbox/b.txt": "short"})
    with pytest.raises(IngestError):
        ingest_file(b, "inbox/a.docx", FakeProvider(DRAFT), language="ko")
    with pytest.raises(IngestError):
        ingest_file(b, "inbox/b.txt", FakeProvider(DRAFT), language="ko")


def test_html_extraction_uses_title_and_drops_scripts(make_brain):
    page = "<html><head><title>Value-up Index</title><script>var x=1</script></head><body><p>The Korea Value-up Index has 100 constituents and starts on Sept 30.</p></body></html>"
    b = make_brain({"inbox/page.html": page})
    provider = FakeProvider({**DRAFT, "key_points": [POINT("100 constituents")]})
    ingest_file(b, "inbox/page.html", provider, language="en")
    user = provider.calls[0][1]
    assert user.startswith("Title (from file metadata): Value-up Index") and "var x" not in user


def test_slugify():
    assert slugify("Korea's Value-up: 2024 Guide!") == "korea-s-value-up-2024-guide"
    assert slugify("한국어 제목") == ""


def test_draft_schema_is_json_schema():
    schema = SourceDraft.model_json_schema()
    assert "source_type" in schema["required"]
    assert isinstance(Path, type)


def test_fetched_link_keeps_its_address(tmp_path):
    from brain_core.history import ensure_repo
    from wooju_agents.capture import remember_link

    ensure_repo(tmp_path)
    (tmp_path / "inbox").mkdir()
    page = tmp_path / "inbox" / "news.html"
    page.write_text(
        "<html><body><p>"
        + "Index news with a footer link https://ads.example.com. " * 5
        + "</p></body></html>",
        encoding="utf-8",
    )
    remember_link(tmp_path, "inbox/news.html", "https://news.example.com/value-up")
    provider = FakeProvider({**DRAFT, "key_points": [POINT("Index news")]})
    proposal = ingest_file(tmp_path, "inbox/news.html", provider, language="en")
    note = next(c for c in proposal.changes if c.path.startswith("sources/")).content
    assert "canonical_ref: https://news.example.com/value-up" in note


def test_title_number_spacing_is_fixed(tmp_path):
    from wooju_agents.ingest import NoteDraft, Point, build_note

    draft = NoteDraft(
        title="경제상황 평가(2026 년 10 월)",
        source_type="docs",
        authors=[],
        published="unknown",
        one_line_summary="요약",
        points=[Point("점", "인용")],
    )
    note = build_note(
        draft, canonical_ref="x", accessed=date(2026, 10, 27), language="en", original_link="y"
    )
    assert "title: 경제상황 평가(2026년 10월)" in note and "# 경제상황 평가(2026년 10월)" in note


def test_without_a_fixed_language_the_note_follows_the_material(brain):
    # ARTICLE is English, so the note is English even if the app is Korean.
    provider = FakeProvider(DRAFT)
    p = ingest_file(brain, "inbox/clip.txt", provider, language=None, ui_language="ko")
    assert "English" in provider.calls[0][0]
    assert "## One-line Summary" in p.changes[0].content


def test_the_note_records_which_model_wrote_it(brain):
    from brain_core.markdown import split_frontmatter

    p = ingest_file(
        brain, "inbox/clip.txt", FakeProvider(DRAFT), language="en", today=date(2026, 10, 27)
    )
    made_by = split_frontmatter(p.changes[0].content)[0]["made_by"]
    assert made_by == [{"agent": "ingest", "did": "created", "on": "2026-10-27", "model": "fake-1"}]


# --- evidence: every key point carries the source's own sentence -------------


def note_of(proposal):
    return next(c for c in proposal.changes if c.path.startswith("sources/")).content


def test_each_key_point_is_followed_by_its_quote(brain):
    p = ingest_file(brain, "inbox/clip.txt", FakeProvider(DRAFT), language="ko")
    note = note_of(p)
    assert "- 802개 중 600개 종목\n  > " in note
    quote = note.split("  > ", 1)[1].splitlines()[0]
    assert "600 of 802 stocks." in quote
    assert quote.replace("\\[", "[") in " ".join(ARTICLE.split())
    applied = apply_proposal(brain, p)
    assert applied.status == "applied", applied.error
    assert validate_brain(brain).ok


def test_a_point_without_its_passage_gets_one_fix(brain):
    draft = {**DRAFT, "key_points": [{"text": "600 of 802", "first": 40, "last": 40}]}

    class Fixing(FakeProvider):
        def answer(self, schema_title, user):
            if schema_title == "Fixes":
                n = passage_with(user, "600 of 802")
                return {"fixes": [{"point": 1, "first": n, "last": n}]}
            return super().answer(schema_title, user)

    provider = Fixing(draft)
    note = note_of(ingest_file(brain, "inbox/clip.txt", provider, language="en"))
    assert len(provider.calls) == 2 and "600 of 802 stocks" in note


def test_points_the_source_does_not_state_are_left_out(brain):
    draft = {
        **DRAFT,
        "key_points": [
            {"text": "600 of 802 stocks", "cite": "600 of 802"},
            {"text": "90% of stocks fell", "cite": "75% of KOSPI"},  # 90 is not there
            {"text": "Nowhere", "first": 50, "last": 50},
        ],
    }
    provider = FakeProvider(draft, fixes=[{"point": 3, "first": None, "last": None}])
    note = note_of(ingest_file(brain, "inbox/clip.txt", provider, language="en"))
    assert "600 of 802 stocks" in note and "90%" not in note and "Nowhere" not in note


def test_no_point_with_evidence_is_an_error(brain):
    draft = {**DRAFT, "key_points": [{"text": "Invented", "first": 99, "last": 99}]}
    with pytest.raises(IngestError) as exc:
        ingest_file(brain, "inbox/clip.txt", FakeProvider(draft), language="en")
    assert exc.value.key == "ingest.no_evidence"


def test_a_quote_cannot_become_markdown(tmp_path):
    from wooju_agents.ingest import NoteDraft, Point, build_note

    draft = NoteDraft(
        title="T",
        source_type="article",
        authors=[],
        published="unknown",
        one_line_summary="s",
        points=[Point("p", "# Not a heading [[link]]"), Point("q", "1. not a list")],
    )
    note = build_note(
        draft, canonical_ref="x", accessed=date(2026, 10, 28), language="en", original_link="y"
    )
    assert "  > \\# Not a heading \\[\\[link]]" in note
    assert "  > \\1. not a list" in note


# --- long sources are read in parts --------------------------------------------

LONG = "\n\n".join(
    f"Section {i}. The index rose {i}% in month {i} as buyers returned to large banks."
    for i in range(1, 1201)
)


class Parts(FakeProvider):
    """Cites the first passage of each part; combines by choosing everything."""

    name = "ollama"

    def __init__(self, fail_on_call=None):
        super().__init__({})
        self.fail_on_call = fail_on_call

    def generate_json(self, system, user, schema):
        from wooju_agents.llm import LLMError

        self.calls.append((system, user, schema))
        if self.fail_on_call == len(self.calls):
            raise LLMError("busy", "llm.busy", retryable=True)
        title = schema.get("title")
        if title == "Combined":
            count = len(re.findall(r"^\d+\. ", user, re.M))
            data = {
                "one_line_summary": "Banks led.",
                "chosen": list(range(1, count + 1)),
                "limitations": [],
            }
        else:
            first = int(re.search(r"\[(\d+)\] Section (\d+)\.", user).group(1))
            section = re.search(r"\[\d+\] Section (\d+)\.", user).group(1)
            data = {
                "key_points": [
                    {"text": f"Rose {section}% in month {section}", "first": first, "last": first}
                ]
            }
            if title == "FirstPart":
                data |= {
                    "title": "Index Diary",
                    "source_type": "docs",
                    "authors": [],
                    "published": "unknown",
                }
        return LLMResult(data, "", 0.01, self.name, self.model)


def test_a_long_source_is_read_in_parts_to_the_end(tmp_path):
    from brain_core.history import ensure_repo
    from wooju_agents.ingest import IngestRun

    ensure_repo(tmp_path)
    (tmp_path / "inbox").mkdir()
    (tmp_path / "inbox" / "long.txt").write_text(LONG, encoding="utf-8")
    provider = Parts()
    run = IngestRun(tmp_path, "inbox/long.txt", provider, language="en")
    assert 1 < len(run.parts) <= 16 and run.steps == len(run.parts) + 1
    while not run.finished:
        run.step()
    note = note_of(run.proposal())
    assert all(estimate_tokens(user) < 6000 for _, user, _ in provider.calls)
    assert provider.calls[-1][2]["title"] == "Combined"
    assert run.passages[run.parts[-1].start] in note  # the last part was read too
    assert note.count("\n  > ") == len(run.parts)
    assert "first part was read" not in note


def test_a_failed_step_continues_where_it_stopped(tmp_path):
    from brain_core.history import ensure_repo
    from wooju_agents.ingest import IngestRun
    from wooju_agents.llm import LLMError

    ensure_repo(tmp_path)
    (tmp_path / "inbox").mkdir()
    (tmp_path / "inbox" / "long.txt").write_text(LONG, encoding="utf-8")
    first = Parts(fail_on_call=3)
    run = IngestRun(tmp_path, "inbox/long.txt", first, language="en")
    with pytest.raises(LLMError):
        while not run.finished:
            run.step()
    assert run.done == 2

    second = Parts()
    again = IngestRun(tmp_path, "inbox/long.txt", second, language="en")
    assert again.done == 2
    while not again.finished:
        again.step()
    again.proposal()
    assert len(second.calls) == again.steps - 2
    again.forget()
    assert IngestRun(tmp_path, "inbox/long.txt", Parts(), language="en").done == 0


def test_a_source_longer_than_the_limit_says_so(tmp_path, monkeypatch):
    from brain_core.history import ensure_repo
    from wooju_agents import ingest

    monkeypatch.setattr(ingest, "MAX_PARTS", 2)
    ensure_repo(tmp_path)
    (tmp_path / "inbox").mkdir()
    (tmp_path / "inbox" / "long.txt").write_text(LONG, encoding="utf-8")
    note = note_of(ingest.ingest_file(tmp_path, "inbox/long.txt", Parts(), language="en"))
    assert "only its first part was read" in note


def test_too_few_combined_points_are_topped_up_across_the_source(tmp_path):
    from brain_core.history import ensure_repo
    from wooju_agents.ingest import IngestRun

    class Stingy(Parts):
        def generate_json(self, system, user, schema):
            if schema.get("title") == "Combined":
                self.calls.append((system, user, schema))
                data = {"one_line_summary": "Banks led.", "chosen": [1], "limitations": []}
                return LLMResult(data, "", 0.01, self.name, self.model)
            return super().generate_json(system, user, schema)

    ensure_repo(tmp_path)
    (tmp_path / "inbox").mkdir()
    long = "\n\n".join(LONG.split("\n\n") * 3)
    (tmp_path / "inbox" / "long.txt").write_text(long, encoding="utf-8")
    run = IngestRun(tmp_path, "inbox/long.txt", Stingy(), language="en")
    while not run.finished:
        run.step()
    kept = [p for part in run._state["parts"] for p in part["points"]]
    draft = run.draft()
    assert len(kept) > 6 and len(draft.points) == 6
    assert draft.points[0].text == kept[0]["text"]  # the model's own pick stays
    assert draft.points[-1].text != kept[5]["text"]  # the rest is spread, not the first six
