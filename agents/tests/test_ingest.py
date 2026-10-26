from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from brain_core import history
from brain_core.changes import apply_proposal
from brain_core.validate import validate_brain
from wooju_agents.ingest import IngestError, SourceDraft, inbox_files, ingest_file, slugify
from wooju_agents.llm import LLMResult

ARTICLE = """KOSPI 75% below book value (Seoul Economic Daily, 2026-07-29)
https://en.sedaily.com/finance/2026/07/29/75-percent-of-kospi-stocks
75% of KOSPI stocks trade below book value as the correction deepens. 600 of 802 stocks.
"""


class FakeProvider:
    name, model = "fake", "fake-1"

    def __init__(self, data):
        self.data, self.calls = data, []

    def generate_json(self, system, user, schema):
        self.calls.append((system, user, schema))
        return LLMResult(self.data, "", 0.01, self.name, self.model)


DRAFT = {
    "title": "75% of KOSPI Stocks Trade Below Book Value",
    "source_type": "article",
    "authors": ["Seoul Economic Daily", " "],
    "published": "2026-07-29",
    "one_line_summary": "2026 년 7 월 29 일 코스피 종목의 75%가 PBR 1 배 미만이다.",
    "key_points": ["802 개 중 600 개 종목"],
    "limitations": ["업종별 수치는 없다."],
}


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
        b, "inbox/notes.md", FakeProvider({**DRAFT, "title": "가치 제고 메모"}), language="ko"
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
    provider = FakeProvider(DRAFT)
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
    proposal = ingest_file(tmp_path, "inbox/news.html", FakeProvider(DRAFT), language="en")
    note = next(c for c in proposal.changes if c.path.startswith("sources/")).content
    assert "canonical_ref: https://news.example.com/value-up" in note


def test_title_number_spacing_is_fixed(tmp_path):
    from datetime import date

    from wooju_agents.ingest import SourceDraft, build_note

    draft = SourceDraft.model_validate({**DRAFT, "title": "경제상황 평가(2026 년 10 월)"})
    note = build_note(
        draft, canonical_ref="x", accessed=date(2026, 10, 27), language="en", original_link="y"
    )
    assert "title: 경제상황 평가(2026년 10월)" in note and "# 경제상황 평가(2026년 10월)" in note
