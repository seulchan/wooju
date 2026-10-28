from __future__ import annotations

from wooju_agents import evidence as ev


def test_wrapped_pdf_lines_join_and_sentences_split():
    text = (
        "Rereading feels productive, but in the study it did\n"
        "little for recall a week later. Testing yourself did more.\n"
        "\n"
        "Results\n"
        "Students who recalled first remembered 50% more after seven days of waiting."
    )
    items = ev.passages(text)
    assert items[0] == (
        "Rereading feels productive, but in the study it did little for recall a week later."
    )
    assert items[1].startswith("Testing yourself did more.")
    assert any("50% more" in p and p.startswith("Results") for p in items)


def test_korean_sentences_split_at_the_period():
    items = ev.passages(
        "코스피 종목의 75%가 장부가 아래에서 거래된다고 기사는 전했다. "
        "802개 중 600개 종목이 여기에 해당하며 은행주가 가장 많았다고 덧붙였다."
    )
    assert len(items) == 2 and items[1].startswith("802개 중 600개")


def test_long_sentences_are_cut_at_words():
    items = ev.passages("word " * 300)
    assert all(len(p) <= ev.MAX_PASSAGE_CHARS for p in items)
    assert " ".join(items).split() == ["word"] * 300


def test_parts_fit_the_budget_and_cover_everything():
    items = [f"Sentence number {i} says something worth keeping." for i in range(500)]
    groups = ev.parts(items, 300)
    assert groups[0].start == 0 and groups[-1].stop == 500
    assert all(a.stop == b.start for a, b in zip(groups, groups[1:], strict=False))
    assert all(ev.estimate_tokens(ev.render(items, g)) <= 300 for g in groups)


def test_quotes_must_be_a_short_run_inside_the_part():
    items = [f"Passage {i}." for i in range(1, 11)]
    part = range(2, 6)  # passages 3..6
    assert ev.quote(items, part, 3, 4).text == "Passage 3. Passage 4."
    assert ev.quote(items, part, 4, None).text == "Passage 4."
    assert ev.quote(items, part, 2, 2) is None  # outside the part
    assert ev.quote(items, part, 3, 6) is None  # four passages
    assert ev.quote(items, part, 5, 4) is None
    assert ev.quote(items, part, True, True) is None
    assert ev.quote(items, part, "3", "3") is None


def test_numbers_in_a_point_must_be_in_its_quote():
    quote = "600 of 802 stocks, or 74.8%, traded below 1,000 won."
    assert ev.numbers_found("600 of 802 stocks", quote)
    assert ev.numbers_found("74.8% traded below 1000 won", quote)
    assert not ev.numbers_found("75% of stocks", quote)
    assert ev.numbers_found("Most stocks are cheap", quote)
