import pytest

from brain_core.markdown import set_frontmatter_value, split_frontmatter

NOTE = "---\ntitle: 테스트  # 메모\nreview_after: 2026-01-01\ntags: [a]\n---\n# 본문\n"


def test_replace_keeps_everything_else():
    out = set_frontmatter_value(NOTE, "review_after", "2027-01-27")
    assert out == NOTE.replace("2026-01-01", "2027-01-27")


def test_add_and_remove():
    added = set_frontmatter_value("---\ntitle: x\n---\nbody\n", "review_after", "2027-01-01")
    assert split_frontmatter(added)[0]["review_after"].isoformat() == "2027-01-01"
    removed = set_frontmatter_value(NOTE, "review_after", None)
    assert "review_after" not in removed and "tags: [a]" in removed


def test_no_frontmatter_and_unclosed():
    assert set_frontmatter_value("# x\n", "review_after", "2027-01-01").startswith(
        "---\nreview_after"
    )
    with pytest.raises(ValueError):
        set_frontmatter_value("---\ntitle: x\n", "review_after", "2027-01-01")


def test_heading_is_shown_and_original_title_kept(tmp_path):
    from brain_core.index import BrainIndex

    (tmp_path / "sources").mkdir()
    (tmp_path / "sources" / "a.md").write_text(
        '---\ntitle: "Korea Value-up Index to begin publication"\nsource_type: article\n'
        "canonical_ref: x\n---\n# 코리아 밸류업 지수 산출 개시\n\n본문\n",
        encoding="utf-8",
    )
    (tmp_path / "sources" / "b.md").write_text(
        "---\ntitle: Same\nsource_type: article\ncanonical_ref: x\n---\n# Same\n\n본문\n",
        encoding="utf-8",
    )
    index = BrainIndex()
    index.scan(tmp_path)
    a = index.get("sources/a")
    assert a.title == "코리아 밸류업 지수 산출 개시"
    assert a.original_title == "Korea Value-up Index to begin publication"
    assert index.get("sources/b").original_title is None
    # The original title is still searchable.
    assert [r.id for _, r in index.search("Value-up publication")] == ["sources/a"]


def test_replace_body_keeps_frontmatter_exactly():
    from brain_core.markdown import replace_body

    text = "---\ntitle: x  # 메모\ntags: [a]\n---\n# x\n\n옛 본문\n"
    out = replace_body(text, "# x\r\n\r\n새 본문\n\n\n")
    assert out == "---\ntitle: x  # 메모\ntags: [a]\n---\n\n# x\n\n새 본문\n"
    assert replace_body("# 없음\n", "새") == "새\n"
